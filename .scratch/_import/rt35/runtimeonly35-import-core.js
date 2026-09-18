(() => {
  'use strict';

  const FIELD_DEFS = [
    { key: 'id', label: '编号', aliases: ['id','编号','序号','任务编号','邮件编号','rowid','taskid','no','number'] },
    { key: 'recipients', label: '收件人', aliases: ['收件人','收件邮箱','收件人邮箱','邮箱','邮箱地址','邮件地址','教授邮箱','导师邮箱','联系邮箱','email','emailaddress','recipient','recipients','to','toemail','contactemail'] },
    { key: 'school', label: '学校 / 机构', aliases: ['学校','院校','大学','高校','机构','单位','所属学校','所属院校','导师学校','教授学校','学校名称','院校名称','机构名称','university','school','institution','organisation','organization','affiliation','universityname','institutionname'] },
    { key: 'subject', label: '主题', aliases: ['主题','邮件主题','标题','subject','title','emailsubject','邮件标题','邮件名称','邮件名','邮件题目'] },
    { key: 'body', label: '正文', aliases: ['正文','邮件正文','内容','邮件内容','正文内容','body','content','message','text','emailbody','邮件文本'] },
    { key: 'attachments', label: '附件', aliases: ['附件','附件名','附件名称','附件路径','附件文件','附件列表','材料','文件','attachment','attachments','file','files','filename','filenames','filepath','documents'] },
    { key: 'scheduleAt', label: '定时时间', aliases: [
      '定时时间','定时发送时间','定时发送','定时','定时日期','预约发送时间','预约时间','预约发送','排期','排期时间','邮件排期','发送排期',
      '发送时间','发送日期','发送日期时间','计划发送时间','计划发送日期','计划发送日期时间','预定发送时间','预定发送日期','投递时间','投递日期',
      'schedule','scheduleat','scheduledat','scheduledtime','scheduleddate','scheduleddatetime','scheduleddelivery','scheduleddeliverytime',
      'sendat','sendtime','senddate','senddatetime','deliverytime','deliverydate','deliverydatetime','plannedsendtime','planneddeliverytime','datetime'
    ] },
    { key: 'tags', label: '任务标记', aliases: ['标签','邮件标签','联系人标签','任务标签','批次','分组','类别','分类','tag','tags','label','labels','group','batch','category','categories'] }
  ];

  const FIELD_KEYS = FIELD_DEFS.map(x => x.key);
  const CORE_FIELDS = ['recipients','subject','body','attachments','scheduleAt'];

  function normalizeHeader(value) {
    return String(value ?? '')
      .trim().toLowerCase().normalize('NFKC')
      .replace(/[\s\u00a0\u200b\u200c\u200d\ufeff_\-—–:：()（）\[\]【】<>《》\/\\.]+/g, '')
      .replace(/[?？!！,，;；]/g, '');
  }

  const ALIAS_LOOKUP = (() => {
    const map = new Map();
    for (const field of FIELD_DEFS) for (const alias of field.aliases) map.set(normalizeHeader(alias), field.key);
    return map;
  })();

  function headerCandidates(value) {
    const h = normalizeHeader(value);
    if (!h) return [];
    const out = [];
    const exact = ALIAS_LOOKUP.get(h);
    if (exact) out.push({ field: exact, score: 100, reason: 'header-exact' });
    for (const def of FIELD_DEFS) {
      for (const raw of def.aliases) {
        const alias = normalizeHeader(raw);
        if (!alias || alias.length < 2) continue;
        let score = 0;
        if (h === alias) score = 100;
        else if (h.includes(alias)) score = 76 + Math.min(18, alias.length);
        else if (alias.includes(h) && h.length >= 3) score = 58 + Math.min(16, h.length);
        if (score) out.push({ field: def.key, score, reason: 'header-fuzzy' });
      }
    }
    const best = new Map();
    for (const item of out) if (!best.has(item.field) || best.get(item.field).score < item.score) best.set(item.field, item);
    return [...best.values()].sort((a,b) => b.score-a.score);
  }

  function matchHeader(value) { return headerCandidates(value)[0] || null; }

  function parseDateLoose(value) {
    if (value instanceof Date && !Number.isNaN(value.getTime())) return value;
    if (typeof value === 'number' && value > 1000 && value < 100000) {
      const utc = Math.round((value - 25569) * 86400 * 1000);
      const d = new Date(utc);
      return Number.isNaN(d.getTime()) ? null : new Date(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate(), d.getUTCHours(), d.getUTCMinutes(), d.getUTCSeconds());
    }
    const raw = String(value ?? '').trim();
    if (!raw) return null;
    if (/^\d+(?:\.\d+)?$/.test(raw)) {
      const n = Number(raw);
      if (n > 1000 && n < 100000) return parseDateLoose(n);
    }
    const normalized = raw.replace(/[年\/.]/g, '-').replace(/月/g, '-').replace(/日/g, ' ').replace(/\s+/g, ' ').trim();
    const m = normalized.match(/^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T](\d{1,2})(?::(\d{1,2}))?(?::(\d{1,2}))?)?$/);
    if (m) {
      const d = new Date(+m[1], +m[2]-1, +m[3], +(m[4]||0), +(m[5]||0), +(m[6]||0));
      return Number.isNaN(d.getTime()) ? null : d;
    }
    const native = new Date(raw);
    return Number.isNaN(native.getTime()) ? null : native;
  }

  function isEmail(v) {
    const s = String(v ?? '').trim();
    if (!s) return false;
    const emails = s.split(/[;,，；\n]+/).map(x => x.trim()).filter(Boolean);
    return emails.length > 0 && emails.every(x => /^[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+$/.test(x.replace(/^.*<([^>]+)>.*$/, '$1')));
  }

  function looksLikeAttachment(v) {
    const s = String(v ?? '').trim();
    if (!s) return false;
    const parts = s.split(/[;；|\n]+/).map(x=>x.trim()).filter(Boolean);
    if (!parts.length) return false;
    return parts.filter(x => /\.(pdf|docx?|xlsx?|pptx?|txt|csv|zip|rar|7z|jpg|jpeg|png|gif|webp)$/i.test(x) || /[\\/]/.test(x)).length / parts.length >= .6;
  }

  function profileColumn(values) {
    const sample = values.filter(v => v !== '' && v != null).slice(0, 80);
    if (!sample.length) return { nonEmpty:0, emailRatio:0, dateRatio:0, attachmentRatio:0, avgLength:0, uniqueRatio:0, shortRatio:0 };
    const strings = sample.map(v => String(v));
    const lengths = strings.map(s => s.length);
    return {
      nonEmpty: sample.length,
      emailRatio: sample.filter(isEmail).length / sample.length,
      dateRatio: sample.filter(v => !!parseDateLoose(v)).length / sample.length,
      attachmentRatio: sample.filter(looksLikeAttachment).length / sample.length,
      avgLength: lengths.reduce((a,b)=>a+b,0)/lengths.length,
      uniqueRatio: new Set(strings).size / strings.length,
      shortRatio: lengths.filter(n=>n<=20).length / lengths.length,
      multilineRatio: strings.filter(s=>/\n/.test(s)).length / strings.length,
      delimiterRatio: strings.filter(s=>/[;；|,，]/.test(s)).length / strings.length
    };
  }

  function dataCandidates(profile) {
    const out = [];
    if (profile.emailRatio >= .55) out.push({ field:'recipients', score: 70 + Math.round(profile.emailRatio*25), reason:'data-email' });
    if (profile.dateRatio >= .55) out.push({ field:'scheduleAt', score: 64 + Math.round(profile.dateRatio*25), reason:'data-date' });
    if (profile.attachmentRatio >= .5) out.push({ field:'attachments', score: 62 + Math.round(profile.attachmentRatio*25), reason:'data-file' });
    if (profile.avgLength >= 120) out.push({ field:'body', score: Math.min(91, 68 + Math.round((profile.avgLength-120)/20)), reason:'data-longtext' });
    else if (profile.avgLength >= 45 && profile.multilineRatio >= .15) out.push({ field:'body', score: 72, reason:'data-multiline' });
    if (profile.avgLength >= 8 && profile.avgLength <= 120 && profile.emailRatio < .2 && profile.dateRatio < .2 && profile.attachmentRatio < .2) out.push({ field:'subject', score: 54 + Math.round(Math.min(18, profile.shortRatio*18)), reason:'data-shorttext' });
    if (profile.uniqueRatio > .85 && profile.shortRatio > .8 && profile.avgLength <= 18 && profile.emailRatio < .2 && profile.dateRatio < .2) out.push({ field:'id', score: 50 + Math.round(profile.uniqueRatio*20), reason:'data-id' });
    if (profile.delimiterRatio >= .45 && profile.avgLength <= 80 && profile.emailRatio < .2 && profile.attachmentRatio < .3) out.push({ field:'tags', score: 52 + Math.round(profile.delimiterRatio*20), reason:'data-tags' });
    return out.sort((a,b)=>b.score-a.score);
  }

  function analyzeColumns(headers, dataRows) {
    const width = Math.max(headers.length, ...dataRows.slice(0,80).map(r=>r?.length||0), 0);
    const cols = [];
    for (let i=0;i<width;i++) {
      const profile = profileColumn(dataRows.map(r=>r?.[i]));
      const candidates = [...headerCandidates(headers[i] ?? ''), ...dataCandidates(profile)];
      const merged = new Map();
      for (const c of candidates) {
        // header is more reliable; combine modestly when both evidence sources agree.
        const prev = merged.get(c.field);
        if (!prev) merged.set(c.field, {...c});
        else merged.set(c.field, { field:c.field, score: Math.min(100, Math.max(prev.score,c.score) + Math.round(Math.min(prev.score,c.score)*.12)), reason:`${prev.reason}+${c.reason}` });
      }
      cols.push({ index:i, header:String(headers[i]??'').trim(), profile, candidates:[...merged.values()].sort((a,b)=>b.score-a.score) });
    }
    return cols;
  }

  function assignFields(columns) {
    const pool = [];
    for (const col of columns) for (const c of col.candidates) pool.push({ ...c, index: col.index });
    pool.sort((a,b)=>b.score-a.score || a.index-b.index);
    const mapping = {}, confidence = {}, evidence = {};
    const usedFields = new Set(), usedColumns = new Set();
    for (const item of pool) {
      if (item.score < 48 || usedFields.has(item.field) || usedColumns.has(item.index)) continue;
      mapping[item.field] = item.index;
      confidence[item.field] = item.score;
      evidence[item.field] = item.reason;
      usedFields.add(item.field); usedColumns.add(item.index);
    }
    return { mapping, confidence, evidence };
  }

  function recognizeAtRow(rows, rowIndex) {
    const headers = (rows[rowIndex] || []).map((v,i)=>String(v??'').trim() || `列${i+1}`);
    const dataRows = rows.slice(rowIndex+1, rowIndex+81);
    const columns = analyzeColumns(headers, dataRows);
    const assigned = assignFields(columns);
    const recognized = Object.keys(assigned.mapping).length;
    const core = CORE_FIELDS.filter(k=>assigned.mapping[k]!=null).length;
    const headerEvidence = Object.values(assigned.evidence).filter(x=>String(x).includes('header')).length;
    const avgConfidence = recognized ? Object.values(assigned.confidence).reduce((a,b)=>a+b,0)/recognized : 0;
    const nonEmpty = headers.filter(Boolean).length;
    const score = recognized*900 + core*230 + headerEvidence*100 + avgConfidence*5 + Math.min(nonEmpty,30) - rowIndex*4;
    return { index:rowIndex, headers, ...assigned, columns, recognized, core, score, avgConfidence };
  }

  function detectHeader(rows) {
    const limit = Math.min(rows.length, 50);
    let best = null;
    for (let i=0;i<limit;i++) {
      if (!(rows[i]||[]).some(v=>String(v??'').trim())) continue;
      const result = recognizeAtRow(rows, i);
      if (!best || result.score > best.score) best = result;
    }
    if (best) return best;
    const index = Math.max(0, rows.findIndex(r=>(r||[]).some(v=>String(v??'').trim())));
    const headers = (rows[index]||[]).map((v,i)=>String(v??'').trim()||`列${i+1}`);
    return { index, headers, mapping:{}, confidence:{}, evidence:{}, columns:[], recognized:0, core:0, score:0, avgConfidence:0 };
  }

  function detectBestSheet(sheets) {
    let best = null;
    (sheets||[]).forEach((sheet,index)=>{
      const detection = detectHeader(sheet.rows||[]);
      const dataRows = Math.max(0,(sheet.rows||[]).length-detection.index-1);
      const score = detection.score + Math.min(dataRows,800);
      if (!best || score>best.score) best={index,detection,score};
    });
    return best || { index:0, detection:detectHeader([]), score:0 };
  }

  function detectBestRecordSet(recordSets) { return detectBestSheet(recordSets); }

  function mappingForHeaders(headers) { return assignFields(analyzeColumns(headers, [])).mapping; }

  function normalizeRows(rows) {
    const out = [];
    for (const row of rows||[]) {
      const a = Array.isArray(row) ? [...row] : [];
      while (a.length && (a[a.length-1] == null || String(a[a.length-1]).trim()==='')) a.pop();
      out.push(a);
    }
    while (out.length && !out[out.length-1].some(v=>String(v??'').trim())) out.pop();
    return out;
  }

  class NormalizedRecordSet {
    constructor({name='Data', rows=[], source=null, meta={}}={}) {
      this.name=name; this.rows=normalizeRows(rows); this.source=source; this.meta=meta;
    }
    fingerprint() {
      const d=detectHeader(this.rows);
      const headers=d.headers.map(normalizeHeader).filter(Boolean).sort();
      const typeSig=(d.columns||[]).map(c=>{
        const p=c.profile; if(p.emailRatio>.6)return'e'; if(p.dateRatio>.6)return'd'; if(p.attachmentRatio>.5)return'f'; if(p.avgLength>120)return'l'; return't';
      }).join('');
      return `${headers.join('|')}::${typeSig}`;
    }
  }

  class NormalizedDataset {
    constructor({recordSets=[], sourceFiles=[], embeddedFiles=[], warnings=[], format='unknown', meta={}}={}) {
      this.sheets = recordSets.map(rs => rs instanceof NormalizedRecordSet ? rs : new NormalizedRecordSet(rs));
      this.recordSets = this.sheets;
      this.sourceFiles=sourceFiles; this.embeddedFiles=embeddedFiles; this.warnings=warnings; this.format=format; this.meta=meta;
    }
  }

  function confidenceLabel(score) { return score>=90?'高':score>=70?'中':'低'; }

  function profileSimilarity(a,b) {
    if (!a || !b) return 0;
    const ah=new Set((a.headers||[]).map(normalizeHeader).filter(Boolean));
    const bh=new Set((b.headers||[]).map(normalizeHeader).filter(Boolean));
    const union=new Set([...ah,...bh]);
    let inter=0; for(const x of ah) if(bh.has(x)) inter++;
    const j=union.size?inter/union.size:0;
    const formatBonus = a.format && b.format && a.format === b.format ? 0.12 : 0;
    return Math.min(1,j+formatBonus);
  }

  globalThis.NMDAImportCore={
    FIELD_DEFS, FIELD_KEYS, CORE_FIELDS, normalizeHeader, matchHeader, mappingForHeaders,
    parseDateLoose, detectHeader, detectBestSheet, detectBestRecordSet, analyzeColumns, profileColumn,
    NormalizedRecordSet, NormalizedDataset, confidenceLabel, profileSimilarity, normalizeRows
  };
})();
