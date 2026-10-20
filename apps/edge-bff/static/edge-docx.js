/* EDGE share card as a Word document (user 2026-10-20: "Tambahkan opsi untuk save as WORD", ".docx asli"). No library:
   the card's DOM (headings, paragraphs with bold/italic, lists, tables, the question box, the logo) becomes WordprocessingML
   and the parts are stored in a ZIP without compression. Loaded on first use, like html-to-image.js.
   EdgeDocx.build({logo, date, meta, question, questionLabel, body, foot}) → Promise<Blob>
   logo: PNG bytes (Uint8Array) and its size in CSS px; body: the card body element; the rest are texts. */
(() => {
  const W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main';
  const esc = text => String(text).replace(/[&<>"]/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;'})[c])
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, '');
  const EMU = 9525;  // per CSS px at 96 dpi

  // ---- runs and paragraphs ----
  function run(text, f = {}) {
    if (!text) return '';
    const props = [f.bold && '<w:b/>', f.italic && '<w:i/>', f.mono && '<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>',
      f.color && `<w:color w:val="${f.color}"/>`, f.size && `<w:sz w:val="${f.size}"/><w:szCs w:val="${f.size}"/>`].filter(Boolean).join('');
    return `<w:r>${props ? `<w:rPr>${props}</w:rPr>` : ''}<w:t xml:space="preserve">${esc(text)}</w:t></w:r>`;
  }
  function para(runs, p = {}) {
    const props = [p.align && `<w:jc w:val="${p.align}"/>`, p.shade && `<w:shd w:val="clear" w:color="auto" w:fill="${p.shade}"/>`,
      `<w:spacing w:before="${p.before ?? 0}" w:after="${p.after ?? 120}"/>`, p.indent && `<w:ind w:left="${p.indent}" w:hanging="${p.hanging || 0}"/>`,
      p.border && '<w:pBdr><w:top w:val="single" w:sz="4" w:space="6" w:color="DDDDDD"/></w:pBdr>',
      p.tabs && `<w:tabs><w:tab w:val="right" w:pos="${p.tabs}"/></w:tabs>`].filter(Boolean).join('');
    return `<w:p><w:pPr>${props}</w:pPr>${runs}</w:p>`;
  }
  // the inline runs of a node: bold, italic and code kept; line breaks kept
  function inline(node, f = {}) {
    let out = '';
    for (const child of node.childNodes) {
      if (child.nodeType === 3) { out += run(child.textContent.replace(/\s+/g, ' '), f); continue; }
      if (child.nodeType !== 1) continue;
      const tag = child.tagName.toLowerCase();
      if (['svg', 'img', 'button', 'script', 'style'].includes(tag)) continue;
      if (tag === 'br') { out += '<w:r><w:br/></w:r>'; continue; }
      out += inline(child, {...f, bold:f.bold || tag === 'strong' || tag === 'b', italic:f.italic || tag === 'em' || tag === 'i',
        mono:f.mono || tag === 'code'});
    }
    return out;
  }
  const BLOCK = new Set(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'table', 'details', 'summary', 'div', 'section',
    'article', 'blockquote', 'pre', 'header', 'footer']);
  const HEADING = {h1:32, h2:28, h3:24, h4:22, h5:21, h6:21};

  function table(node) {
    const rows = [...node.querySelectorAll('tr')];
    if (!rows.length) return '';
    const cols = Math.max(...rows.map(r => r.cells.length));
    const width = Math.floor(9360 / Math.max(cols, 1));
    const border = '<w:top w:val="single" w:sz="4" w:color="D9D9D9"/><w:left w:val="nil"/><w:bottom w:val="single" w:sz="4" w:color="D9D9D9"/><w:right w:val="nil"/><w:insideH w:val="single" w:sz="4" w:color="D9D9D9"/><w:insideV w:val="nil"/>';
    const grid = `<w:tblGrid>${('<w:gridCol w:w="' + width + '"/>').repeat(cols)}</w:tblGrid>`;
    const body = rows.map(row => {
      const head = row.parentElement?.tagName === 'THEAD' || [...row.cells].every(c => c.tagName === 'TH');
      return `<w:tr>${head ? '<w:trPr><w:tblHeader/></w:trPr>' : ''}${[...row.cells].map(cell => {
        const right = cell.classList.contains('num');
        return `<w:tc><w:tcPr><w:tcW w:w="${width}" w:type="dxa"/>${head ? '<w:shd w:val="clear" w:color="auto" w:fill="F1F1F4"/>' : ''}</w:tcPr>`
          + para(inline(cell, {bold:head, size:18}), {after:0, align:right ? 'right' : undefined}) + '</w:tc>';
      }).join('')}</w:tr>`;
    }).join('');
    return `<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:tblBorders>${border}</w:tblBorders><w:tblCellMar><w:top w:w="60" w:type="dxa"/><w:left w:w="100" w:type="dxa"/><w:bottom w:w="60" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar></w:tblPr>${grid}${body}</w:tbl>`
      + para('', {after:120});
  }
  function list(node, depth) {
    const ordered = node.tagName === 'OL';
    let n = 0, out = '';
    for (const item of node.children) {
      if (item.tagName !== 'LI') continue;
      n += 1;
      const nested = [...item.children].filter(c => c.tagName === 'UL' || c.tagName === 'OL');
      const own = item.cloneNode(true);
      own.querySelectorAll(':scope > ul, :scope > ol').forEach(c => c.remove());
      out += para(run((ordered ? n + '.' : '•') + '\t') + inline(own), {indent:360 * (depth + 1), hanging:300, after:60});
      nested.forEach(c => { out += list(c, depth + 1); });
    }
    return out;
  }
  // the block content of a node, in order
  function blocks(node) {
    let out = '', loose = '';
    const flush = () => { if (loose.replace(/<[^>]+>/g, '').trim()) out += para(loose); loose = ''; };
    for (const child of node.childNodes) {
      if (child.nodeType === 3) { loose += run(child.textContent.replace(/\s+/g, ' ')); continue; }
      if (child.nodeType !== 1) continue;
      const tag = child.tagName.toLowerCase();
      if (['svg', 'img', 'button', 'script', 'style'].includes(tag)) continue;
      if (!BLOCK.has(tag) && !child.querySelector('p,table,ul,ol,h1,h2,h3,h4,div')) { loose += inline(child); continue; }
      flush();
      if (HEADING[tag]) out += para(inline(child, {bold:true, size:HEADING[tag]}), {before:200, after:100});
      else if (tag === 'p') out += para(inline(child));
      else if (tag === 'ul' || tag === 'ol') out += list(child, 0);
      else if (tag === 'table') out += table(child);
      else if (tag === 'summary') out += para(inline(child, {bold:true, color:'555555', size:20}), {before:160, after:60});
      else if (tag === 'pre') out += para(run(child.textContent, {mono:true, size:18}));
      else out += blocks(child);
    }
    flush();
    return out;
  }

  // ---- the document ----
  function documentXml(card, logo) {
    const picture = logo ? (() => {
      const cx = Math.round(logo.width * EMU), cy = Math.round(logo.height * EMU);
      return `<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="${cx}" cy="${cy}"/><wp:docPr id="1" name="EDGE"/>`
        + `<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">`
        + `<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:nvPicPr><pic:cNvPr id="0" name="edge-logo.png"/><pic:cNvPicPr/></pic:nvPicPr>`
        + `<pic:blipFill><a:blip r:embed="rIdLogo"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="${cx}" cy="${cy}"/></a:xfrm>`
        + `<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>`;
    })() : run('EDGE', {bold:true, size:28});
    const parts = [
      para(picture + '<w:r><w:tab/></w:r>' + run(card.date, {color:'717182', size:18}), {tabs:9360, after:200}),
      card.meta ? para(run(card.meta, {color:'717182', size:17}), {after:200}) : '',
      para(run(card.questionLabel, {color:'BBBBBB', size:17}), {shade:'030213', after:0, before:0}),
      para(run(card.question, {color:'FFFFFF', size:20}), {shade:'030213', after:240}),
      blocks(card.body),
      card.foot.length ? para(card.foot.map((line, i) => (i ? '<w:r><w:br/></w:r>' : '') + run(line, {color:'717182', size:17})).join(''),
        {border:true, before:240}) : '',
    ];
    return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="${W}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">`
      + `<w:body>${parts.join('')}<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1080" w:right="1440" w:bottom="1080" w:left="1440" w:header="708" w:footer="708" w:gutter="0"/></w:sectPr></w:body></w:document>`;
  }
  const STYLES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="${W}"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="Calibri" w:cs="Calibri"/><w:sz w:val="21"/><w:szCs w:val="21"/><w:lang w:val="id-ID"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style></w:styles>`;
  const TYPES = logo => `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>${logo ? '<Default Extension="png" ContentType="image/png"/>' : ''}<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>`;
  const RELS = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>`;
  const DOC_RELS = logo => `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>${logo ? '<Relationship Id="rIdLogo" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/edge-logo.png"/>' : ''}</Relationships>`;

  // ---- a ZIP of stored (uncompressed) files ----
  const CRC = (() => { const t = new Uint32Array(256); for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xEDB88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; })();
  const crc32 = bytes => { let c = 0xFFFFFFFF; for (let i = 0; i < bytes.length; i++) c = CRC[(c ^ bytes[i]) & 0xFF] ^ (c >>> 8); return (c ^ 0xFFFFFFFF) >>> 0; };
  function zip(files) {
    const enc = new TextEncoder(), chunks = [], central = [];
    let offset = 0;
    for (const [name, content] of files) {
      const data = typeof content === 'string' ? enc.encode(content) : content, path = enc.encode(name), crc = crc32(data);
      const local = new DataView(new ArrayBuffer(30));
      [[0, 0x04034b50, 4], [4, 20, 2], [6, 0x0800, 2], [8, 0, 2], [10, 0, 2], [12, 0x21, 2], [14, crc, 4], [18, data.length, 4],
        [22, data.length, 4], [26, path.length, 2], [28, 0, 2]].forEach(([at, v, size]) => size === 4 ? local.setUint32(at, v, true) : local.setUint16(at, v, true));
      const entry = new DataView(new ArrayBuffer(46));
      [[0, 0x02014b50, 4], [4, 20, 2], [6, 20, 2], [8, 0x0800, 2], [10, 0, 2], [12, 0, 2], [14, 0x21, 2], [16, crc, 4], [20, data.length, 4],
        [24, data.length, 4], [28, path.length, 2], [30, 0, 2], [32, 0, 2], [34, 0, 2], [36, 0, 2], [38, 0, 4], [42, offset, 4]]
        .forEach(([at, v, size]) => size === 4 ? entry.setUint32(at, v, true) : entry.setUint16(at, v, true));
      chunks.push(new Uint8Array(local.buffer), path, data);
      central.push(new Uint8Array(entry.buffer), path);
      offset += 30 + path.length + data.length;
    }
    const size = central.reduce((s, c) => s + c.length, 0), end = new DataView(new ArrayBuffer(22));
    [[0, 0x06054b50, 4], [4, 0, 2], [6, 0, 2], [8, files.length, 2], [10, files.length, 2], [12, size, 4], [16, offset, 4], [20, 0, 2]]
      .forEach(([at, v, s]) => s === 4 ? end.setUint32(at, v, true) : end.setUint16(at, v, true));
    return new Blob([...chunks, ...central, new Uint8Array(end.buffer)],
      {type:'application/vnd.openxmlformats-officedocument.wordprocessingml.document'});
  }

  window.EdgeDocx = {
    build(card) {
      const logo = card.logo && card.logo.bytes ? card.logo : null;
      return zip([['[Content_Types].xml', TYPES(logo)], ['_rels/.rels', RELS], ['word/document.xml', documentXml(card, logo)],
        ['word/styles.xml', STYLES], ['word/_rels/document.xml.rels', DOC_RELS(logo)], ...(logo ? [['word/media/edge-logo.png', logo.bytes]] : [])]);
    },
    _xml: documentXml,
  };
})();
