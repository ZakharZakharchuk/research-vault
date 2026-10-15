// Збирання звіту в .docx за ДСТУ 3008:2015: РЕФЕРАТ → СКОРОЧЕННЯ ТА УМОВНІ ПОЗНАКИ → розділ 1 →
// ПЕРЕЛІК ДЖЕРЕЛ ПОСИЛАННЯ. A4, Times New Roman 14, інтервал 1,5, абзацний відступ 1,25 см,
// поля 20/20/30/15 мм, номер сторінки праворуч угорі; відстань між заголовком і текстом —
// два міжрядкові інтервали (п. 7.1.24), між двома заголовками поспіль — як у тексті.
// Виклик: node build.js [вихідний.docx]
const fs = require('fs');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, Table, TableRow, TableCell,
  WidthType, BorderStyle, Header, PageNumber, PageBreak, ShadingType,
} = require('docx');

const data = JSON.parse(fs.readFileSync('doc.json', 'utf8'));
const FONT = 'Times New Roman';
const MM = 56.7; // DXA на мм
const PAGE_W = 11906, ML = Math.round(30 * MM), MR = Math.round(15 * MM);
const TEXT_W = PAGE_W - ML - MR;
const INDENT = 709; // 1,25 см
const HSPACE = 640; // ≈ два міжрядкові інтервали кегля 14 (2 × 16 пт)
const OUT = process.argv[2] || 'ch1.docx';

// Інлайн-розмітка: **жирний**, `код`, ⟦примітка автора⟧
function runs(text, base = {}) {
  const out = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|⟦[^⟧]+⟧)/g;
  let last = 0, m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) out.push(new TextRun({ text: text.slice(last, m.index), ...base }));
    const tok = m[0];
    if (tok.startsWith('**')) out.push(new TextRun({ text: tok.slice(2, -2), bold: true, ...base }));
    else if (tok.startsWith('`')) out.push(new TextRun({ text: tok.slice(1, -1), ...base }));
    else out.push(new TextRun({ text: '[' + tok.slice(1, -1) + ']', highlight: 'yellow', italics: true, ...base }));
    last = m.index + tok.length;
  }
  if (last < text.length) out.push(new TextRun({ text: text.slice(last), ...base }));
  return out;
}

const bodyPara = (text) => new Paragraph({
  children: runs(text), alignment: AlignmentType.JUSTIFIED,
  indent: { firstLine: INDENT }, spacing: { line: 360, before: 0, after: 0 },
});

function colWidths(rows) {
  const n = rows[0].length;
  const score = Array(n).fill(0);
  rows.forEach(r => r.forEach((c, i) => { score[i] += Math.sqrt(c.length + 4); }));
  const minW = n >= 6 ? 1000 : 1400;
  let total = score.reduce((a, b) => a + b, 0);
  let w = score.map(s => Math.max(minW, Math.round(TEXT_W * s / total)));
  const sum = w.reduce((a, b) => a + b, 0);
  w = w.map(x => Math.floor(x * TEXT_W / sum));
  w[n - 1] += TEXT_W - w.reduce((a, b) => a + b, 0);
  return w;
}

function table(rows) {
  const widths = colWidths(rows);
  const border = { style: BorderStyle.SINGLE, size: 4, color: '000000' };
  const borders = { top: border, bottom: border, left: border, right: border };
  return new Table({
    width: { size: TEXT_W, type: WidthType.DXA },
    columnWidths: widths,
    rows: rows.map((r, ri) => new TableRow({
      tableHeader: ri === 0, cantSplit: true,
      children: r.map((c, ci) => new TableCell({
        width: { size: widths[ci], type: WidthType.DXA },
        borders,
        margins: { top: 40, bottom: 40, left: 80, right: 80 },
        shading: ri === 0 ? { type: ShadingType.CLEAR, fill: 'F2F2F2', color: 'auto' } : undefined,
        children: [new Paragraph({
          alignment: ri === 0 ? AlignmentType.CENTER : AlignmentType.LEFT,
          spacing: { line: 240, before: 0, after: 0 },
          keepNext: ri < rows.length - 1, keepLines: true,
          children: runs(c, { size: 24, bold: ri === 0 ? true : undefined }),
        })],
      })),
    })),
  });
}

const structHeading = (text) => new Paragraph({
  heading: HeadingLevel.HEADING_1, alignment: AlignmentType.CENTER,
  spacing: { line: 360, before: 0, after: HSPACE }, children: [new TextRun(text)],
});

const children = [];
// ТИТУЛЬНИЙ АРКУШ (входить до нумерації, номер не проставляють — ДСТУ 3008:2015, п. 7.3.3)
const T = data.title || {};
if (Object.keys(T).length) {
  const c = (text, opt = {}) => new Paragraph({
    alignment: opt.align || AlignmentType.CENTER, spacing: { line: opt.line || 300, before: opt.before || 0, after: opt.after || 0 },
    indent: opt.indent, children: runs(text || '', { bold: opt.bold, size: opt.size }),
  });
  children.push(c(T['міністерство']));
  children.push(c(T['університет'], { bold: true }));
  children.push(c(T['підрозділ'], { before: 120 }));
  children.push(c(T['кафедра']));
  children.push(c(T['вид'], { bold: true, size: 32, before: 2400, after: 120 }));
  children.push(c(T['дисципліна'], { after: 360 }));
  children.push(c('на тему:'));
  children.push(c(T['тема'], { bold: true, after: 1800 }));
  const right = { align: AlignmentType.LEFT, indent: { left: Math.round(TEXT_W * 0.45) } };
  children.push(c(T['виконав'], right));
  children.push(c(T['виконавець'], { ...right, after: 360 }));
  children.push(c(T['керівник'], right));
  children.push(c(T['керівник_пріз'], right));
  children.push(c(T['місто_рік'], { before: 2000 }));
  children.push(new Paragraph({ children: [new PageBreak()] }));
}
// РЕФЕРАТ
if (data.abstract && data.abstract.length) {
  for (const b of data.abstract) {
    if (b.t === 'h1') children.push(structHeading(b.text));
    else children.push(bodyPara(b.text));
  }
  children.push(new Paragraph({ children: [new PageBreak()] }));
}
if (data.abbr && data.abbr.length) {
  children.push(structHeading('СКОРОЧЕННЯ ТА УМОВНІ ПОЗНАКИ'));
  const nb = { style: BorderStyle.NONE, size: 0, color: 'FFFFFF' };
  const nbs = { top: nb, bottom: nb, left: nb, right: nb, insideHorizontal: nb, insideVertical: nb };
  const w1 = 2000, w2 = TEXT_W - w1;
  children.push(new Table({
    width: { size: TEXT_W, type: WidthType.DXA }, columnWidths: [w1, w2], borders: nbs,
    rows: data.abbr.map(([a, b]) => new TableRow({ children: [
      new TableCell({ width: { size: w1, type: WidthType.DXA }, borders: nbs,
        children: [new Paragraph({ spacing: { line: 360, before: 0, after: 0 }, children: [new TextRun(a)] })] }),
      new TableCell({ width: { size: w2, type: WidthType.DXA }, borders: nbs,
        children: [new Paragraph({ spacing: { line: 360, before: 0, after: 0 }, alignment: AlignmentType.LEFT, children: [new TextRun('— ' + b)] })] }),
    ] })),
  }));
  children.push(new Paragraph({ children: [new PageBreak()] }));
}
let firstH1 = true;
const isH = (x) => x && ['h1', 'h2', 'h3'].includes(x.t);
data.blocks.forEach((b, bi) => {
  const prevH = isH(data.blocks[bi - 1]), nextH = isH(data.blocks[bi + 1]);
  if (b.t === 'h1') {
    const m = b.text.match(/^(РОЗДІЛ \d+)\.?\s*(.*)$/);
    children.push(new Paragraph({
      heading: HeadingLevel.HEADING_1, alignment: AlignmentType.CENTER,
      spacing: { line: 360, before: 0, after: nextH ? 0 : HSPACE },
      children: m ? [new TextRun({ text: m[1] }), new TextRun({ text: m[2], break: 1 })] : [new TextRun(b.text)],
    }));
    firstH1 = false;
  } else if (b.t === 'h2') {
    children.push(new Paragraph({
      heading: HeadingLevel.HEADING_2, indent: { firstLine: INDENT },
      spacing: { line: 360, before: prevH ? 0 : HSPACE, after: nextH ? 0 : HSPACE }, keepNext: true, children: runs(b.text),
    }));
  } else if (b.t === 'h3') {
    children.push(new Paragraph({
      heading: HeadingLevel.HEADING_3, indent: { firstLine: INDENT },
      spacing: { line: 360, before: prevH ? 0 : HSPACE, after: nextH ? 0 : HSPACE }, keepNext: true, children: runs(b.text),
    }));
  } else if (b.t === 'caption') {
    children.push(new Paragraph({
      indent: { firstLine: INDENT }, spacing: { line: 360, before: 240, after: 120 },
      keepNext: true, children: runs(b.text),
    }));
  } else if (b.t === 'table') {
    children.push(table(b.rows));
    children.push(new Paragraph({ spacing: { line: 240, before: 0, after: 120 }, children: [] }));
  } else if (b.t === 'note') {
    children.push(new Paragraph({
      indent: { firstLine: INDENT }, spacing: { line: 240, before: 0, after: 240 },
      alignment: AlignmentType.JUSTIFIED, children: runs(b.text, { size: 24 }),
    }));
  } else {
    children.push(bodyPara(b.text));
  }
});

// Перелік посилань
children.push(new Paragraph({ children: [new PageBreak()] }));
children.push(structHeading('ПЕРЕЛІК ДЖЕРЕЛ ПОСИЛАННЯ'));
data.refs.forEach((r, i) => children.push(new Paragraph({
  alignment: AlignmentType.JUSTIFIED, indent: { firstLine: INDENT },
  spacing: { line: 360, before: 0, after: 0 },
  children: [new TextRun(`${i + 1}. ${r}`)],
})));

const doc = new Document({
  creator: T['виконавець'] || '',
  title: T['тема'] || 'Звіт',
  styles: {
    default: { document: { run: { font: FONT, size: 28 }, paragraph: { spacing: { line: 360 } } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: FONT, size: 28, bold: true, allCaps: true, color: '000000' },
        paragraph: { outlineLevel: 0, keepNext: true } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: FONT, size: 28, bold: true, color: '000000' }, paragraph: { outlineLevel: 1, keepNext: true } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true,
        run: { font: FONT, size: 28, bold: true, color: '000000' }, paragraph: { outlineLevel: 2, keepNext: true } },
    ],
  },
  sections: [{
    properties: {
      titlePage: !!(data.title && Object.keys(data.title).length),
      page: {
        size: { width: PAGE_W, height: 16838 },
        margin: { top: Math.round(20 * MM), bottom: Math.round(20 * MM), left: ML, right: MR, header: 567 },
      },
    },
    headers: {
      first: new Header({ children: [new Paragraph({ children: [] })] }),
      default: new Header({ children: [new Paragraph({
        alignment: AlignmentType.RIGHT,
        children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 28 })],
      })] }),
    },
    children,
  }],
});

Packer.toBuffer(doc).then(buf => { fs.writeFileSync(OUT, buf); console.log('ok', OUT, buf.length); });
