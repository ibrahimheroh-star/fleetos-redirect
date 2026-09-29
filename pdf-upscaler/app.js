(function () {
  'use strict';

  // ---------- عناصر الواجهة ----------
  var $ = function (id) { return document.getElementById(id); };
  var fileInput = $('file'), drop = $('drop'), thumbs = $('thumbs'), goBtn = $('go');
  var progressBox = $('progress'), statusEl = $('status'), barFill = $('barFill');
  var resultBox = $('result'), resultInfo = $('resultInfo'), dlLink = $('dl');
  var shareBtn = $('share'), dlImgBtn = $('dlImg'), previewImg = $('preview');
  var sharpInput = $('sharp'), sharpVal = $('sharpVal');

  var files = [];
  var busy = false;
  var pdfUrl = null, previewUrl = null, firstUpscaledBlob = null, pdfFile = null;

  var IS_MOBILE = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);
  // حد أقصى لعدد بكسلات الصورة المكبّرة (المتصفحات على الجوال تحدّ حجم الـ canvas)
  var MAX_PIXELS = IS_MOBILE ? 16e6 : 48e6;
  // أكبر ضلع للصورة المرسلة إلى OCR
  var OCR_MAX_SIDE = 3500;
  // نسبة تحويل بكسل → نقطة PDF: الصورة الأصلية تُعرض بـ 96 dpi
  var PT_PER_ORIGINAL_PX = 0.75;

  var ARABIC_RE = /[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]/;

  // ---------- أدوات عامة ----------
  function tick() { return new Promise(function (r) { setTimeout(r, 0); }); }

  function setProgress(frac, text) {
    progressBox.style.display = 'block';
    if (text) statusEl.textContent = text;
    barFill.style.width = Math.max(0, Math.min(1, frac)) * 100 + '%';
  }

  function showError(msg) {
    progressBox.style.display = 'block';
    statusEl.innerHTML = '';
    var s = document.createElement('span');
    s.className = 'error';
    s.textContent = msg;
    statusEl.appendChild(s);
  }

  function fetchBytes(url) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error('تعذّر تحميل ' + url);
      return r.arrayBuffer();
    });
  }

  function canvasToBlob(canvas, type, quality) {
    return new Promise(function (resolve, reject) {
      canvas.toBlob(function (b) {
        b ? resolve(b) : reject(new Error('فشل إنشاء الصورة (ربما الصورة كبيرة جدًا على هذا الجهاز)'));
      }, type, quality);
    });
  }

  function loadImage(file) {
    return new Promise(function (resolve, reject) {
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onload = function () { URL.revokeObjectURL(url); resolve(img); };
      img.onerror = function () { URL.revokeObjectURL(url); reject(new Error('تعذّر فتح الصورة: ' + file.name)); };
      img.src = url;
    });
  }

  // ---------- اختيار الملفات ----------
  function renderThumbs() {
    thumbs.innerHTML = '';
    files.forEach(function (f, i) {
      var d = document.createElement('div');
      d.className = 'thumb';
      var img = document.createElement('img');
      var u = URL.createObjectURL(f);
      img.onload = function () { URL.revokeObjectURL(u); };
      img.src = u;
      var b = document.createElement('button');
      b.type = 'button';
      b.textContent = '×';
      b.setAttribute('aria-label', 'حذف');
      b.onclick = function () { if (!busy) { files.splice(i, 1); renderThumbs(); } };
      d.appendChild(img); d.appendChild(b);
      thumbs.appendChild(d);
    });
    goBtn.disabled = busy || files.length === 0;
  }

  function addFiles(list) {
    Array.prototype.forEach.call(list, function (f) {
      if (/^image\//.test(f.type)) files.push(f);
    });
    renderThumbs();
  }

  drop.addEventListener('click', function () { fileInput.click(); });
  drop.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); } });
  fileInput.addEventListener('change', function () { addFiles(fileInput.files); fileInput.value = ''; });
  ['dragenter', 'dragover'].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add('over'); });
  });
  ['dragleave', 'drop'].forEach(function (ev) {
    drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove('over'); });
  });
  drop.addEventListener('drop', function (e) { addFiles(e.dataTransfer.files); });
  sharpInput.addEventListener('input', function () { sharpVal.textContent = sharpInput.value; });

  // ---------- التكبير (Lanczos-3) ----------
  function lanczos(x) {
    if (x === 0) return 1;
    if (x <= -3 || x >= 3) return 0;
    var px = Math.PI * x;
    return 3 * Math.sin(px) * Math.sin(px / 3) / (px * px);
  }

  // أوزان إعادة العيّنة لبُعد واحد: لكل بكسل ناتج 6 عيّنات من المصدر
  function makeWeights(srcLen, dstLen) {
    var ratio = dstLen / srcLen;
    var idx = new Int32Array(dstLen * 6);
    var wts = new Float32Array(dstLen * 6);
    for (var i = 0; i < dstLen; i++) {
      var center = (i + 0.5) / ratio - 0.5;
      var base = Math.floor(center);
      var sum = 0;
      for (var k = 0; k < 6; k++) {
        var j = base - 2 + k;
        var w = lanczos(center - j);
        sum += w;
        wts[i * 6 + k] = w;
        idx[i * 6 + k] = Math.min(srcLen - 1, Math.max(0, j));
      }
      for (var k2 = 0; k2 < 6; k2++) wts[i * 6 + k2] /= sum;
    }
    return { idx: idx, wts: wts };
  }

  // src: Uint8ClampedArray RGBA بحجم sw×sh  →  Uint8ClampedArray RGBA بحجم dw×dh
  async function resizeLanczos(src, sw, sh, dw, dh, onProgress) {
    var wx = makeWeights(sw, dw), wy = makeWeights(sh, dh);
    var tmp = new Uint8ClampedArray(dw * sh * 4);
    var last = performance.now();
    var x, y, k, c;

    // أفقي
    for (y = 0; y < sh; y++) {
      var rowS = y * sw * 4, rowD = y * dw * 4;
      for (x = 0; x < dw; x++) {
        var r = 0, g = 0, b = 0, xi = x * 6;
        for (k = 0; k < 6; k++) {
          var w = wx.wts[xi + k], p = rowS + wx.idx[xi + k] * 4;
          r += src[p] * w; g += src[p + 1] * w; b += src[p + 2] * w;
        }
        var o = rowD + x * 4;
        tmp[o] = r; tmp[o + 1] = g; tmp[o + 2] = b; tmp[o + 3] = 255;
      }
      if (performance.now() - last > 40) { last = performance.now(); onProgress((y / sh) * 0.4); await tick(); }
    }

    // عمودي
    var out = new Uint8ClampedArray(dw * dh * 4);
    for (y = 0; y < dh; y++) {
      var yi = y * 6, rowO = y * dw * 4;
      for (x = 0; x < dw; x++) {
        var r2 = 0, g2 = 0, b2 = 0, col = x * 4;
        for (k = 0; k < 6; k++) {
          var w2 = wy.wts[yi + k], p2 = wy.idx[yi + k] * dw * 4 + col;
          r2 += tmp[p2] * w2; g2 += tmp[p2 + 1] * w2; b2 += tmp[p2 + 2] * w2;
        }
        var o2 = rowO + col;
        out[o2] = r2; out[o2 + 1] = g2; out[o2 + 2] = b2; out[o2 + 3] = 255;
      }
      if (performance.now() - last > 40) { last = performance.now(); onProgress(0.4 + (y / dh) * 0.5); await tick(); }
    }
    void c;
    return out;
  }

  // Unsharp mask خفيف لاستعادة حدّة الحواف بعد التكبير
  async function unsharp(data, w, h, sigma, amount, onProgress) {
    var radius = Math.max(1, Math.ceil(sigma * 3));
    var kernel = new Float32Array(radius * 2 + 1), ks = 0, i;
    for (i = -radius; i <= radius; i++) { kernel[i + radius] = Math.exp(-(i * i) / (2 * sigma * sigma)); ks += kernel[i + radius]; }
    for (i = 0; i < kernel.length; i++) kernel[i] /= ks;

    var tmp = new Uint8ClampedArray(data.length), blur = new Uint8ClampedArray(data.length);
    var last = performance.now(), x, y, t;

    for (y = 0; y < h; y++) {
      var row = y * w * 4;
      for (x = 0; x < w; x++) {
        var r = 0, g = 0, b = 0;
        for (t = -radius; t <= radius; t++) {
          var xx = Math.min(w - 1, Math.max(0, x + t)), p = row + xx * 4, kw = kernel[t + radius];
          r += data[p] * kw; g += data[p + 1] * kw; b += data[p + 2] * kw;
        }
        var o = row + x * 4;
        tmp[o] = r; tmp[o + 1] = g; tmp[o + 2] = b;
      }
      if (performance.now() - last > 40) { last = performance.now(); onProgress((y / h) * 0.5); await tick(); }
    }
    for (y = 0; y < h; y++) {
      for (x = 0; x < w; x++) {
        var r2 = 0, g2 = 0, b2 = 0;
        for (t = -radius; t <= radius; t++) {
          var yy = Math.min(h - 1, Math.max(0, y + t)), p2 = (yy * w + x) * 4, kw2 = kernel[t + radius];
          r2 += tmp[p2] * kw2; g2 += tmp[p2 + 1] * kw2; b2 += tmp[p2 + 2] * kw2;
        }
        var o2 = (y * w + x) * 4;
        blur[o2] = r2; blur[o2 + 1] = g2; blur[o2 + 2] = b2;
      }
      if (performance.now() - last > 40) { last = performance.now(); onProgress(0.5 + (y / h) * 0.4); await tick(); }
    }
    for (i = 0; i < data.length; i += 4) {
      data[i] += amount * (data[i] - blur[i]);
      data[i + 1] += amount * (data[i + 1] - blur[i + 1]);
      data[i + 2] += amount * (data[i + 2] - blur[i + 2]);
    }
  }

  // يرجع { canvas, scale } للصورة المكبّرة
  async function upscaleImage(img, wantedScale, sharp, onProgress) {
    var sw = img.naturalWidth, sh = img.naturalHeight;
    var scale = Math.min(wantedScale, Math.sqrt(MAX_PIXELS / (sw * sh)));
    if (scale < 1) scale = 1;
    var dw = Math.round(sw * scale), dh = Math.round(sh * scale);

    var c0 = document.createElement('canvas');
    c0.width = sw; c0.height = sh;
    var x0 = c0.getContext('2d', { willReadFrequently: true });
    x0.fillStyle = '#fff'; // الشفافية تُدمج على خلفية بيضاء
    x0.fillRect(0, 0, sw, sh);
    x0.drawImage(img, 0, 0);
    var src = x0.getImageData(0, 0, sw, sh).data;

    var canvas = document.createElement('canvas');
    canvas.width = dw; canvas.height = dh;
    var ctx = canvas.getContext('2d');

    if (scale === 1) {
      ctx.drawImage(c0, 0, 0);
      return { canvas: canvas, scale: 1 };
    }

    var data = await resizeLanczos(src, sw, sh, dw, dh, function (f) { onProgress(f * (sharp > 0 ? 0.7 : 1)); });
    if (sharp > 0) {
      await unsharp(data, dw, dh, Math.max(0.8, scale * 0.35), sharp * 0.9, function (f) { onProgress(0.7 + f * 0.3); });
    }
    ctx.putImageData(new ImageData(data, dw, dh), 0, 0);
    return { canvas: canvas, scale: scale };
  }

  // ---------- OCR ----------
  var ocrWorker = null, ocrLang = null, ocrProgressCb = null;

  async function getOcrWorker(lang) {
    if (ocrWorker && ocrLang === lang) return ocrWorker;
    if (ocrWorker) { await ocrWorker.terminate(); ocrWorker = null; }
    var abs = function (p) { return new URL(p, location.href).href; };
    ocrWorker = await Tesseract.createWorker(lang, 1, {
      workerPath: abs('vendor/worker.min.js'),
      corePath: abs('vendor/core/'),
      langPath: abs('vendor/lang/'),
      workerBlobURL: false,
      gzip: true,
      logger: function (m) { if (ocrProgressCb && m.status === 'recognizing text') ocrProgressCb(m.progress); }
    });
    ocrLang = lang;
    return ocrWorker;
  }

  function flattenLines(data) {
    var lines = [];
    (data.blocks || []).forEach(function (b) {
      (b.paragraphs || []).forEach(function (p) {
        (p.lines || []).forEach(function (l) { lines.push(l); });
      });
    });
    if (!lines.length && data.lines) lines = data.lines;
    if (!lines.length && data.words) lines = [{ words: data.words, bbox: null }];
    return lines;
  }

  // يرجع مصفوفة أسطر: { words:[{text,x0,y0,x1,y1}], y0, y1, rtl }
  async function runOcr(canvas, lang, onProgress) {
    var ratio = Math.min(1, OCR_MAX_SIDE / Math.max(canvas.width, canvas.height));
    var src = canvas;
    if (ratio < 1) {
      src = document.createElement('canvas');
      src.width = Math.round(canvas.width * ratio);
      src.height = Math.round(canvas.height * ratio);
      var sctx = src.getContext('2d');
      sctx.imageSmoothingQuality = 'high';
      sctx.drawImage(canvas, 0, 0, src.width, src.height);
    }
    var worker = await getOcrWorker(lang);
    ocrProgressCb = onProgress;
    var res = await worker.recognize(src, {}, { blocks: true });
    ocrProgressCb = null;

    var inv = 1 / ratio;
    var out = [];
    flattenLines(res.data).forEach(function (l) {
      var words = [];
      (l.words || []).forEach(function (w) {
        var text = (w.text || '').replace(/[‎‏‪-‮⁦-⁩]/g, '').trim();
        if (!text || !w.bbox || (w.confidence !== undefined && w.confidence < 25)) return;
        words.push({ text: text, x0: w.bbox.x0 * inv, y0: w.bbox.y0 * inv, x1: w.bbox.x1 * inv, y1: w.bbox.y1 * inv });
      });
      if (!words.length) return;
      var arabicChars = 0, otherChars = 0;
      words.forEach(function (w) {
        for (var i = 0; i < w.text.length; i++) {
          if (ARABIC_RE.test(w.text[i])) arabicChars++; else if (/[A-Za-z]/.test(w.text[i])) otherChars++;
        }
      });
      var rtl = arabicChars > otherChars;
      // ترتيب الكلمات = ترتيب القراءة (لضمان أن النسخ يعطي النص بالترتيب الصحيح)
      words.sort(function (a, b) { return rtl ? b.x0 - a.x0 : a.x0 - b.x0; });
      var y0 = Math.min.apply(null, words.map(function (w) { return w.y0; }));
      var y1 = Math.max.apply(null, words.map(function (w) { return w.y1; }));
      out.push({ words: words, y0: y0, y1: y1, rtl: rtl });
    });
    out.sort(function (a, b) { return a.y0 - b.y0; });
    return out;
  }

  // ---------- PDF ----------
  var fontCache = null;
  async function getFonts(pdf) {
    if (!fontCache) {
      fontCache = {
        ar: await fetchBytes('vendor/fonts/noto-naskh-arabic-arabic-400-normal.woff'),
        la: await fetchBytes('vendor/fonts/noto-naskh-arabic-latin-400-normal.woff')
      };
    }
    pdf.registerFontkit(fontkit);
    // نُعطّل تشكيل الحروف (init/medi/fina...) حتى يبقى النص المنسوخ مطابقًا للنص الأصلي
    var noShaping = {
      init: false, medi: false, fina: false, isol: false, rlig: false, liga: false, ccmp: false,
      calt: false, mark: false, mkmk: false, curs: false, kern: false, locl: false, rclt: false, dlig: false
    };
    var ar = await pdf.embedFont(fontCache.ar, { subset: true, features: noShaping });
    var la = await pdf.embedFont(fontCache.la, { subset: true, features: noShaping });
    return {
      ar: ar, la: la,
      arSet: new Set(ar.getCharacterSet()),
      laSet: new Set(la.getCharacterSet())
    };
  }

  // يقسّم الكلمة إلى مقاطع، كل مقطع بخط يدعم حروفه
  function splitRuns(text, F) {
    var runs = [];
    for (var ch of text) {
      var cp = ch.codePointAt(0), font = null;
      if (ARABIC_RE.test(ch) && F.arSet.has(cp)) font = F.ar;
      else if (F.laSet.has(cp)) font = F.la;
      else if (F.arSet.has(cp)) font = F.ar;
      if (!font) continue;
      var last = runs[runs.length - 1];
      if (last && last.font === font) last.text += ch; else runs.push({ font: font, text: ch });
    }
    return runs;
  }

  // يرسم طبقة النص غير المرئية (Render mode 3) فوق الصورة
  function drawTextLayer(pdf, page, lines, pxToPt, pageH, F) {
    var PL = PDFLib;
    var fontKeys = new Map();
    function fontName(font) {
      if (!fontKeys.has(font)) {
        var key = 'F' + (fontKeys.size + 1);
        page.node.setFontDictionary(PL.PDFName.of(key), font.ref);
        fontKeys.set(font, key);
      }
      return fontKeys.get(font);
    }
    var ops = [];
    lines.forEach(function (line) {
      var lineH = Math.max(1, (line.y1 - line.y0) * pxToPt);
      var size = lineH * 0.8;
      var baseline = pageH - (line.y1 * pxToPt - lineH * 0.2);
      line.words.forEach(function (w, wi) {
        var runs = splitRuns(w.text, F);
        if (!runs.length) return;
        var natural = 0;
        runs.forEach(function (r) { r.width = r.font.widthOfTextAtSize(r.text, size); natural += r.width; });
        if (natural <= 0) return;
        var boxW = (w.x1 - w.x0) * pxToPt;
        var sx = boxW / natural;
        var x = w.x0 * pxToPt;
        runs.forEach(function (r) {
          ops.push(PL.beginText());
          ops.push(PL.setTextRenderingMode(PL.TextRenderingMode.Invisible));
          ops.push(PL.setFontAndSize(fontName(r.font), size));
          ops.push(PL.setTextMatrix(sx, 0, 0, 1, x, baseline));
          ops.push(PL.showText(r.font.encodeText(r.text)));
          ops.push(PL.endText());
          x += r.width * sx;
        });
        // مسافة بين الكلمات لتُنسخ كنص طبيعي
        if (wi < line.words.length - 1) {
          ops.push(PL.beginText());
          ops.push(PL.setTextRenderingMode(PL.TextRenderingMode.Invisible));
          ops.push(PL.setFontAndSize(fontName(F.la), size));
          ops.push(PL.setTextMatrix(1, 0, 0, 1, x, baseline));
          ops.push(PL.showText(F.la.encodeText(' ')));
          ops.push(PL.endText());
        }
      });
      // فاصل سطر
      ops.push(PL.beginText());
      ops.push(PL.setTextRenderingMode(PL.TextRenderingMode.Invisible));
      ops.push(PL.setFontAndSize(fontName(F.la), size));
      ops.push(PL.setTextMatrix(1, 0, 0, 1, 0, baseline));
      ops.push(PL.showText(F.la.encodeText(' ')));
      ops.push(PL.endText());
    });
    page.pushOperators.apply(page, ops);
  }

  // ---------- التشغيل الرئيسي ----------
  async function run() {
    busy = true;
    goBtn.disabled = true;
    resultBox.style.display = 'none';
    var scaleWanted = parseFloat($('scale').value);
    var sharp = parseFloat(sharpInput.value);
    var lang = $('lang').value;
    var fmt = $('fmt').value;
    var wantOcr = $('ocr').checked;
    var n = files.length;
    var warnings = [];

    try {
      var pdf = await PDFLib.PDFDocument.create();
      var F = wantOcr ? await getFonts(pdf) : null;
      var totalWords = 0;
      firstUpscaledBlob = null;

      for (var i = 0; i < n; i++) {
        var base = i / n, span = 1 / n;
        var tag = n > 1 ? ' (' + (i + 1) + '/' + n + ')' : '';

        setProgress(base, 'جاري فتح الصورة' + tag + '...');
        var img = await loadImage(files[i]);
        var ow = img.naturalWidth, oh = img.naturalHeight;

        setProgress(base, 'جاري تكبير الصورة' + tag + '...');
        var up = await upscaleImage(img, scaleWanted, sharp, function (f) {
          setProgress(base + span * 0.35 * f);
        });
        if (up.scale < scaleWanted - 0.01) {
          warnings.push('الصورة ' + (i + 1) + ': التكبير ×' + up.scale.toFixed(2) + ' بدل ×' + scaleWanted + ' (حد حجم الصورة على هذا الجهاز)');
        }

        var lines = [];
        if (wantOcr) {
          setProgress(base + span * 0.35, 'جاري قراءة النص' + tag + ' (أول مرة قد تأخذ وقتًا أطول)...');
          lines = await runOcr(up.canvas, lang, function (f) {
            setProgress(base + span * (0.35 + 0.5 * f));
          });
          lines.forEach(function (l) { totalWords += l.words.length; });
        }

        setProgress(base + span * 0.85, 'جاري بناء صفحة الـ PDF' + tag + '...');
        var blob = await canvasToBlob(up.canvas, fmt === 'png' ? 'image/png' : 'image/jpeg', 0.95);
        if (i === 0) firstUpscaledBlob = blob;
        var bytes = new Uint8Array(await blob.arrayBuffer());
        var image = fmt === 'png' ? await pdf.embedPng(bytes) : await pdf.embedJpg(bytes);

        var pageW = ow * PT_PER_ORIGINAL_PX, pageH = oh * PT_PER_ORIGINAL_PX;
        var page = pdf.addPage([pageW, pageH]);
        page.drawImage(image, { x: 0, y: 0, width: pageW, height: pageH });
        if (wantOcr && lines.length) {
          drawTextLayer(pdf, page, lines, pageW / up.canvas.width, pageH, F);
        }

        up.canvas.width = up.canvas.height = 0; // تحرير الذاكرة
        await tick();
      }

      setProgress(0.97, 'جاري حفظ الملف...');
      var out = await pdf.save();
      var pdfBlob = new Blob([out], { type: 'application/pdf' });
      if (pdfUrl) URL.revokeObjectURL(pdfUrl);
      pdfUrl = URL.createObjectURL(pdfBlob);
      var name = (n === 1 ? files[0].name.replace(/\.[^.]+$/, '') : 'converted') + '.pdf';
      pdfFile = new File([pdfBlob], name, { type: 'application/pdf' });
      dlLink.href = pdfUrl;
      dlLink.download = name;

      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = URL.createObjectURL(firstUpscaledBlob);
      previewImg.src = previewUrl;

      var info = 'الصفحات: ' + n + ' — الحجم: ' + (pdfBlob.size / 1048576).toFixed(1) + ' MB';
      if (wantOcr) info += ' — عدد الكلمات المقروءة: ' + totalWords;
      if (warnings.length) info += '\n' + warnings.join('\n');
      resultInfo.textContent = info;
      resultInfo.style.whiteSpace = 'pre-line';
      resultBox.style.display = 'block';
      shareBtn.style.display = (navigator.canShare && navigator.canShare({ files: [pdfFile] })) ? '' : 'none';
      setProgress(1, 'تم ✅');
    } catch (e) {
      console.error(e);
      showError('حدث خطأ: ' + (e && e.message ? e.message : e));
    } finally {
      busy = false;
      renderThumbs();
    }
  }

  goBtn.addEventListener('click', function () { if (!busy && files.length) run(); });

  shareBtn.addEventListener('click', function () {
    if (pdfFile) navigator.share({ files: [pdfFile], title: pdfFile.name }).catch(function () {});
  });

  dlImgBtn.addEventListener('click', function () {
    if (!firstUpscaledBlob) return;
    var a = document.createElement('a');
    a.href = URL.createObjectURL(firstUpscaledBlob);
    a.download = 'upscaled' + (firstUpscaledBlob.type === 'image/png' ? '.png' : '.jpg');
    document.body.appendChild(a); a.click(); a.remove();
  });

  // للاختبار الآلي
  window.__app = { addFiles: addFiles, upscaleImage: upscaleImage, runOcr: runOcr, loadImage: loadImage };
})();
