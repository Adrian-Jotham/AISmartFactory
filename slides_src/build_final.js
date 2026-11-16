// final.pptx: Part II (predictive maintenance), continuing fault_diagnosis_part1_short.pptx
// Build:  NODE_PATH=<folder with pptxgenjs + jszip>/node_modules node build_final.js ../final.pptx
// SHOW_HIDDEN=1 un-hides the appendix (for checking renders).
const pptxgen = require("pptxgenjs");
const JSZip = require("jszip");
const fs = require("fs");
const { applyTheme } = require("/home/zenith/.claude/skills/synced/5199403c-ac56-4296-8e5e-e26ffd6b78eb_86cede0d-1541-4c33-811a-3b00face1bf0/pptx/scripts/apply_theme.js");

const OUT = process.argv[2] || "final.pptx";
const HEX = {
  ink: "12262B", white: "FFFFFF", teal: "0F4C5C", tint: "EDF5F4",
  coral: "F26B4F", mid: "1F8A8A", grey: "8A9A9B", green: "3E9B5F", red: "D64545", pale: "9CC9C4",
};
const THEME = {
  name: "Bearing PdM", headFontFace: "Calibri", bodyFontFace: "Calibri",
  colors: { dk1: HEX.ink, lt1: HEX.white, dk2: HEX.teal, lt2: HEX.tint, accent1: HEX.coral, accent2: HEX.mid,
    accent3: HEX.grey, accent4: HEX.green, accent5: HEX.red, accent6: HEX.pale, hlink: HEX.mid, folHlink: HEX.grey },
};

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE"; // 13.333 x 7.5, same as Part I
pres.theme = { headFontFace: "Calibri", bodyFontFace: "Calibri" };
pres.title = "Part II: Predictive maintenance";
const C = pres.SchemeColor;
const COL = { ink: C.text1, white: C.background1, teal: C.text2, tint: C.background2, coral: C.accent1,
  mid: C.accent2, grey: C.accent3, green: C.accent4, red: C.accent5, pale: C.accent6 };
const W = 13.333, M = 0.6, CW = W - 2 * M;

// ---------- layouts ----------
pres.defineSlideMaster({
  title: "TITLE", background: { color: COL.teal },
  objects: [{ placeholder: { options: { name: "title", type: "title", x: M, y: 1.7, w: 7.6, h: 2.0,
    fontSize: 40, bold: true, color: COL.white, valign: "bottom", align: "left", margin: 0 }, text: "" } }],
});
for (const [name, foot] of [["CONTENT", "Part II · Predictive maintenance · NASA/IMS bearing data"], ["APPENDIX", "Appendix (hidden backup slide for Q&A)"]]) {
  pres.defineSlideMaster({
    title: name, background: { color: COL.white },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: M, y: 0.52, w: CW, h: 0.85,
        fontSize: 26, bold: true, color: COL.teal, valign: "top", align: "left", margin: 0 }, text: "" } },
      { text: { text: foot, options: { x: M, y: 7.0, w: 8, h: 0.3, fontSize: 11, color: COL.grey, margin: 0 } } },
    ],
    slideNumber: { x: 12.2, y: 7.0, w: 0.53, h: 0.3, fontSize: 11, color: COL.grey, align: "right" },
  });
}

// ---------- helpers ----------
const txt = (s, t, o) => s.addText(t, Object.assign({ isTextBox: true, margin: 0, fontSize: 20, color: COL.ink, valign: "top" }, o));
const box = (s, o) => s.addShape(pres.shapes.ROUNDED_RECTANGLE, Object.assign({ rectRadius: 0.08, line: { color: COL.tint, width: 0 }, fill: { color: COL.tint } }, o));
const rect = (s, o) => s.addShape(pres.shapes.RECTANGLE, o);
const cite = (s, t) => txt(s, t, { x: M, y: 6.6, w: CW, h: 0.3, fontSize: 12, color: COL.grey });
const chev = (s, x, y) => s.addShape(pres.shapes.CHEVRON, { x, y, w: 0.28, h: 0.4, fill: { color: COL.grey }, line: { color: COL.grey } });
const bullets = (items, o) => items.map((b, j) => ({ text: b, options: Object.assign({ bullet: true, breakLine: j < items.length - 1 }, o || {}) }));
const axis = () => ({
  catAxisLabelColor: HEX.ink, valAxisLabelColor: HEX.ink, catAxisLabelFontSize: 16, valAxisLabelFontSize: 16,
  catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt", valAxisTitleFontFace: "+mn-lt", catAxisTitleFontFace: "+mn-lt",
  dataLabelFontFace: "+mn-lt", legendFontFace: "+mn-lt", valAxisTitleColor: HEX.ink, catAxisTitleColor: HEX.ink,
  valAxisTitleFontSize: 16, catAxisTitleFontSize: 16, legendFontSize: 16, legendColor: HEX.ink,
  valGridLine: { color: "DDE5E4", size: 0.75 }, catGridLine: { style: "none" },
  valAxisLineShow: false, catAxisLineColor: HEX.grey,
});
const add = (master, sec, title, notes, kicker) => {
  const s = pres.addSlide({ masterName: master, sectionTitle: sec });
  s.addText(title, { placeholder: "title" });
  txt(s, (kicker || sec).toUpperCase(), { x: M, y: 0.2, w: 8, h: 0.3, fontSize: 12, bold: true, color: COL.coral, charSpacing: 1.5 });
  if (notes) s.addNotes(notes);
  return s;
};
const T = (s, rows, colW, y, o) => s.addTable(rows.map((r, ri) => r.map((c) => {
  const cell = typeof c === "object" && c !== null && c.text !== undefined ? c : { text: String(c) };
  return { text: cell.text, options: Object.assign({ fontSize: (o && o.fs) || 16, color: ri === 0 ? HEX.white : HEX.ink, bold: ri === 0,
    fill: { color: ri === 0 ? HEX.teal : (ri % 2 ? HEX.white : HEX.tint) }, margin: [3, 6, 3, 6], valign: "middle" }, cell.options || {}) };
})), { x: (o && o.x) || M, y, w: (o && o.w) || CW, colW, border: { type: "solid", pt: 0.5, color: "D5DFDE" } });

// =====================================================================
// 1. Title
pres.addSection({ title: "Opening" });
{
  const s = pres.addSlide({ masterName: "TITLE", sectionTitle: "Opening" });
  s.addText("Acting on bearing alarms: which maintenance strategy costs least?", { placeholder: "title" });
  txt(s, "PART II · PREDICTIVE MAINTENANCE", { x: M, y: 1.15, w: 7.6, h: 0.4, fontSize: 16, bold: true, color: COL.coral, charSpacing: 2 });
  txt(s, "Continues Part I: fault diagnosis on the NASA/IMS run-to-failure bearing dataset", { x: M, y: 3.9, w: 7.4, h: 0.8, fontSize: 20, color: COL.pale });
  txt(s, [
    { text: "Adrian Ferdinand Jotham  2026210913", options: { breakLine: true } },
    { text: "Han Yuxin  2026210586", options: { breakLine: true } },
    { text: "Haryadi, Gifar Arif  2025210488" },
  ], { x: M, y: 5.2, w: 7.4, h: 1.1, fontSize: 16, color: COL.white });
  txt(s, "AI-based Fault Diagnosis and Predictive Maintenance for Smart Factories", { x: M, y: 6.6, w: 9, h: 0.35, fontSize: 12, color: COL.pale });
  const cx = 10.6, cy = 3.6, R = 1.9;
  s.addShape(pres.shapes.OVAL, { x: cx - R, y: cy - R, w: 2 * R, h: 2 * R, fill: { color: COL.pale }, line: { color: COL.pale } });
  s.addShape(pres.shapes.OVAL, { x: cx - 1.55, y: cy - 1.55, w: 3.1, h: 3.1, fill: { color: COL.teal }, line: { color: COL.teal } });
  s.addShape(pres.shapes.OVAL, { x: cx - 0.95, y: cy - 0.95, w: 1.9, h: 1.9, fill: { color: COL.pale }, line: { color: COL.pale } });
  s.addShape(pres.shapes.OVAL, { x: cx - 0.6, y: cy - 0.6, w: 1.2, h: 1.2, fill: { color: COL.teal }, line: { color: COL.teal } });
  for (let i = 0; i < 10; i++) {
    const a = (i / 10) * 2 * Math.PI, r = 1.25, b = 0.27;
    s.addShape(pres.shapes.OVAL, { x: cx + r * Math.cos(a) - b, y: cy + r * Math.sin(a) - b, w: 2 * b, h: 2 * b,
      fill: { color: i === 2 ? COL.white : COL.coral }, line: { color: COL.teal, width: 1 } });
  }
  s.addNotes("This is Part II of our project. In Part I we built alarms that find a failing bearing and name the broken part. Today we ask what the factory should do with those alarms, how we decide, and whether acting on them saves money.");
}

// =====================================================================
// 2. Recap Part I
pres.addSection({ title: "Recap of Part I" });
{
  const s = add("CONTENT", "Recap of Part I", "Part I found every failing bearing early and named the broken part",
    "A quick reminder of where Part I left us. Stage A compares each bearing's vibration energy with its neighbours on the same shaft: that tells us which bearing is failing and when. Stage B reads the rhythm of the clicks in the envelope spectrum: that tells us which part is broken. On the four failures, Stage A found all four, a median of 61 hours before the end, and Stage B named all four fault types. Part I stopped at the alarm. Part II starts there: what do we do with it?");
  const cards = [
    ["Stage A · loudness", "Energy vs. the neighbour bearings", "Which bearing? When?"],
    ["Stage B · rhythm", "Envelope spectrum at the fault frequencies", "Which part: outer race, inner race, ball?"],
  ];
  cards.forEach((c, i) => {
    const y = 1.6 + i * 2.0;
    box(s, { x: M, y, w: 6.6, h: 1.7 });
    txt(s, c[0], { x: M + 0.3, y: y + 0.2, w: 6.0, h: 0.45, fontSize: 22, bold: true, color: COL.teal });
    txt(s, c[1], { x: M + 0.3, y: y + 0.7, w: 6.0, h: 0.4, fontSize: 20 });
    txt(s, "→ " + c[2], { x: M + 0.3, y: y + 1.12, w: 6.0, h: 0.4, fontSize: 20, bold: true, color: COL.coral });
  });
  [["4 / 4", "failures found"], ["61 h", "median warning before the end"], ["4 / 4", "fault types named"]].forEach((st, i) => {
    const y = 1.55 + i * 1.3;
    txt(s, st[0], { x: 7.9, y, w: 2.0, h: 0.9, fontSize: 44, bold: true, color: COL.teal, valign: "middle" });
    txt(s, st[1], { x: 9.95, y, w: 2.8, h: 0.9, fontSize: 20, valign: "middle" });
  });
  box(s, { x: M, y: 5.7, w: CW, h: 0.75, fill: { color: COL.teal }, line: { color: COL.teal } });
  txt(s, [{ text: "Part II asks: ", options: { bold: true, color: COL.coral } },
    { text: "when an alarm fires, what should the factory do, and does it save money?", options: { color: COL.white } }],
  { x: M + 0.3, y: 5.7, w: CW - 0.6, h: 0.75, fontSize: 22, valign: "middle" });
}

// =====================================================================
// 3. Problem: three strategies
pres.addSection({ title: "Problem" });
{
  const s = add("CONTENT", "Problem", "A factory can repair after failure, on a schedule, or on an alarm",
    "A factory has three classic options. Reactive: run the bearing until it breaks, then repair. Cheap to run, but every failure is an unplanned breakdown: downtime, damage to the shaft, rush parts. Preventive: replace every T hours. In this dataset bearings failed anywhere between 164 and 1,073 hours, so any single T either throws away healthy bearings or misses early failures. Condition-based: replace when monitoring raises an alarm. That needs alarms that are early and reliable, which is what Part I built. Our question is whether condition-based maintenance with our alarms is actually cheaper on real run-to-failure data.");
  const cards = [
    ["Reactive", "Run to failure, then repair", ["Every failure is an unplanned breakdown", "Downtime, secondary damage"], false],
    ["Preventive", "Replace every T hours", ["Failures came after 164 to 1,073 h", "One T wastes life or misses failures"], false],
    ["Condition-based", "Replace when an alarm fires", ["Needs early, reliable alarms", "Our Part I alarms"], true],
  ];
  cards.forEach((c, i) => {
    const x = M + i * 4.13, w = 3.83, y = 1.6, dark = c[3];
    box(s, { x, y, w, h: 3.55, fill: { color: dark ? COL.teal : COL.tint }, line: { color: dark ? COL.teal : COL.tint } });
    txt(s, c[0], { x: x + 0.3, y: y + 0.3, w: w - 0.6, h: 0.5, fontSize: 24, bold: true, color: dark ? COL.coral : COL.teal });
    txt(s, c[1], { x: x + 0.3, y: y + 0.95, w: w - 0.6, h: 0.5, fontSize: 20, bold: true, color: dark ? COL.white : COL.ink });
    txt(s, bullets(c[2]), { x: x + 0.3, y: y + 1.65, w: w - 0.6, h: 1.7, fontSize: 18, color: dark ? COL.pale : COL.ink, paraSpaceAfter: 6 });
  });
  txt(s, [{ text: "Research question: ", options: { bold: true, color: COL.teal } },
    { text: "on real run-to-failure data, is acting on our alarms cheaper than reactive or preventive maintenance?" }],
  { x: M, y: 5.45, w: CW, h: 0.9, fontSize: 20 });
  cite(s, "Maintenance strategies: Jardine et al., 2006");
}

// =====================================================================
// 4. Related work
{
  const s = add("CONTENT", "Problem", "We build on four lines of research and test two newer ones",
    "This is how our work relates to previous research. Condition-based maintenance is usually described as three steps: acquire data, process it, decide. Most bearing papers stop at the processing step and report accuracy. We do the decide step, with a cost. For diagnosis we use the envelope spectrum, the standard tutorial method, which is our Stage B. For detection we use an autoencoder trained on normal data only, a known anomaly-detection approach. Remaining-life prediction is the textbook next step, but it needs many failure histories; we tried it and report why it did not help. And we tested two recent ideas: foundation models and running on cheap edge hardware.");
  T(s, [
    ["Line of work", "Key paper", "What it does", "How we use it"],
    ["Condition-based maintenance", "Jardine et al., 2006", "Acquire → process → decide", { text: "We do the decide step, with cost", options: { bold: true } }],
    ["Bearing diagnosis", "Randall & Antoni, 2011", "Envelope spectrum at fault frequencies", "Stage B: fault type in the work order"],
    ["Anomaly detection", "Sakurada & Yairi, 2014", "Autoencoder trained on normal data only", "Our AI alarm"],
    ["Remaining-life (RUL) prediction", "Lei et al., 2018", "Hours left; needs many failure histories", "Tried: no gain with 4 failures"],
    ["Foundation models", "Goswami 2024; Eldele 2025", "Large pretrained time-series models", "Tested zero-shot: no gain"],
    ["Edge / TinyML", "Arciniegas et al., 2025", "Monitoring on a small device", "Our alarm on a Raspberry Pi"],
  ], [3.1, 2.6, 3.2, 3.23], 1.55, { fs: 16 });
  txt(s, "Gap: most bearing studies report detection accuracy; few price the maintenance decision on real run-to-failure data.",
    { x: M, y: 6.0, w: CW, h: 0.7, fontSize: 18, color: COL.teal, bold: true });
}

// =====================================================================
// 5. System architecture
pres.addSection({ title: "Method" });
{
  const s = add("CONTENT", "Method", "The system turns raw vibration into a priced work order in five steps",
    "Here is the whole system. One: data. Each bearing has an accelerometer; every 10 minutes the rig records one second at 20 kilohertz. Two: features. Each snapshot becomes 16 numbers. Three: detect and diagnose. Two independent alarms watch for a failing bearing: the physics alarm from Part I Stage A and the AI autoencoder alarm. Stage B names the fault. Four: decide. Whichever alarm fires first opens a work order automatically, with the bearing, the fault and a due time. Five: evaluate. We replay the whole thing in time order on all 12 bearings and price every outcome. The next slides go through each block.");
  const cols = [
    ["1 · Data", ["4 accelerometers", "1 s at 20 kHz, every 10 min"]],
    ["2 · Features", ["16 numbers per snapshot", "energy, impulsiveness, bands, envelope"]],
    ["3 · Detect + diagnose", null],
    ["4 · Decide", ["Either-alarm rule", "Work order: bearing, fault, due time"]],
    ["5 · Evaluate", ["Time-ordered replay, 12 bearings", "Cost per 1,000 h"]],
  ];
  const w = 2.2, gap = 0.28, y = 1.75, h = 3.6;
  cols.forEach((c, i) => {
    const x = M + i * (w + gap);
    txt(s, c[0], { x, y: y - 0.05, w, h: 0.4, fontSize: 18, bold: true, color: COL.teal });
    if (c[1]) {
      box(s, { x, y: y + 0.45, w, h: h - 0.45, fill: { color: i === 3 ? COL.teal : COL.tint }, line: { color: i === 3 ? COL.teal : COL.tint } });
      txt(s, bullets(c[1]), { x: x + 0.15, y: y + 0.65, w: w - 0.3, h: h - 0.8, fontSize: 17, color: i === 3 ? COL.white : COL.ink, paraSpaceAfter: 8 });
    } else {
      const sub = [["Physics alarm", "energy vs. peers (Stage A)"], ["AI alarm", "autoencoder error vs. peers"], ["Stage B", "fault type"]];
      sub.forEach((u, j) => {
        const yy = y + 0.45 + j * 1.07;
        box(s, { x, y: yy, w, h: 0.95, fill: { color: j === 2 ? COL.white : COL.tint }, line: { color: j === 2 ? COL.grey : COL.tint, width: 1 } });
        txt(s, u[0], { x: x + 0.15, y: yy + 0.08, w: w - 0.3, h: 0.35, fontSize: 17, bold: true, color: j === 2 ? COL.teal : COL.coral });
        txt(s, u[1], { x: x + 0.15, y: yy + 0.45, w: w - 0.3, h: 0.45, fontSize: 15 });
      });
    }
    if (i < 4) chev(s, x + w + 0.0, y + 0.45 + (h - 0.45) / 2 - 0.2);
  });
  box(s, { x: M, y: 5.65, w: CW, h: 0.8 });
  txt(s, [{ text: "Design choice: ", options: { bold: true, color: COL.teal } },
    { text: "the replay only uses data up to each moment, exactly as a live plant would see it" }],
  { x: M + 0.3, y: 5.65, w: CW - 0.6, h: 0.8, fontSize: 20, valign: "middle" });
}

// =====================================================================
// 6. Data & features
{
  const s = add("CONTENT", "Method", "Each 1-second snapshot becomes 16 numbers that describe its vibration",
    "The data: three run-to-failure tests on the IMS rig, four bearings each, so 12 bearings. Four failed, eight were still healthy when their test ended. Every 10 minutes the rig records one second of vibration at 20 kilohertz, 20,480 samples per sensor. We reduce each snapshot to 16 features in four groups. Energy: how strong the vibration is. Impulsiveness: how peaky it is, because a crack makes sharp clicks. Band energies: where in frequency the energy sits. Envelope amplitudes at the four fault frequencies from Part I. The physics alarm uses only RMS. The autoencoder uses all 16, log-scaled and standardised. The first 20 percent of every test is treated as the healthy reference.");
  const facts = [["12", "bearings: 3 tests × 4"], ["4", "failed · 8 healthy"], ["20,480", "samples per 1-s snapshot"], ["10 min", "between snapshots"]];
  facts.forEach((f, i) => {
    const y = 1.6 + i * 1.12;
    box(s, { x: M, y, w: 3.4, h: 0.95 });
    txt(s, f[0], { x: M + 0.2, y, w: 1.45, h: 0.95, fontSize: 30, bold: true, color: COL.teal, valign: "middle" });
    txt(s, f[1], { x: M + 1.7, y, w: 1.6, h: 0.95, fontSize: 15, valign: "middle" });
  });
  T(s, [
    ["Group", "Features", "What it captures"],
    ["Energy", "RMS, peak, peak-to-peak", "How strong the vibration is"],
    ["Impulsiveness", "kurtosis, crest, shape, impulse factor", "Sharp clicks from a crack"],
    ["Frequency bands", "centroid; energy 0-1, 1-3, 3-6, 6-10 kHz", "Where the energy sits"],
    ["Envelope", "amplitude at BPFO, BPFI, BSF, FTF", "Fault rhythms (Part I)"],
  ], [1.9, 3.75, 2.75], 1.6, { x: 4.33, w: 8.4, fs: 17 });
  txt(s, bullets(["Physics alarm: RMS only", "AI alarm: all 16, log-scaled and standardised", "Healthy reference: first 20% of each test"]),
    { x: 4.33, y: 4.45, w: 8.4, h: 1.3, fontSize: 18, paraSpaceAfter: 4 });
  cite(s, "BPFO / BPFI / BSF / FTF: outer race, inner race, ball spin and cage frequencies. Dataset: Qiu et al., 2006");
}

// =====================================================================
// 7. Physics alarm
{
  const s = add("CONTENT", "Method", "Physics alarm: a bearing is failing when it grows louder than its neighbours",
    "The physics alarm, Part I Stage A, in four steps. One: a health index, the log of RMS divided by the bearing's own healthy median, so it measures relative growth with no units. It is smoothed by a one-hour running median. Two: peer contrast. We subtract the median health index of the other three bearings. All four share one shaft, load and room, so anything that affects the whole rig cancels out, and what remains is this bearing's own damage. Three: a limit learned from the healthy window: the median plus eight robust standard deviations, but never less than 0.15, which is about 16 percent louder than the peers. The robust standard deviation uses the median absolute deviation, so a few spikes do not inflate it. Four: the contrast must stay above the limit for six snapshots in a row, one hour, so a single spike cannot raise an alarm.");
  const steps = [
    ["Health index", "HI = log( RMS / healthy median RMS )", "Relative growth, no units; 1-h running median"],
    ["Peer contrast", "C = HI − median HI of the other 3 bearings", "Load, temperature, rig-wide changes cancel"],
    ["Limit", "median + max( 8 × robust SD , 0.15 )", "Robust SD = 1.4826 × MAD ignores spikes; 0.15 ≈ 16% louder"],
    ["Persistence", "C > limit for 6 snapshots in a row", "One hour: a single spike cannot alarm"],
  ];
  T(s, [["Step", "Computation", "Why"], ...steps.map((r, i) => [`${i + 1}. ${r[0]}`, { text: r[1], options: { bold: true, color: HEX.teal } }, r[2]])],
    [2.4, 4.9, 4.83], 1.6, { fs: 18 });
  box(s, { x: M, y: 4.3, w: CW, h: 1.45 });
  txt(s, [{ text: "Why peers, not own history: ", options: { bold: true, color: COL.teal } },
    { text: "all 4 bearings share one shaft and housing. Comparing with neighbours removes what they share and leaves the local damage. Trained on nothing but the healthy window." }],
  { x: M + 0.3, y: 4.38, w: CW - 0.6, h: 1.3, fontSize: 18, valign: "middle" });
}

// =====================================================================
// 8. AI alarm
{
  const s = add("CONTENT", "Method", "AI alarm: an autoencoder flags what it cannot rebuild from healthy data",
    "The AI alarm is an autoencoder: a small neural network that squeezes the 16 features into 4 numbers and rebuilds the 16. The layers are 16, 12, 4, 12, 16 with tanh activations: 524 weights in total. We train it only on the healthy window, the first 20 percent of each test, all four bearings pooled, with mean squared error, Adam optimiser, learning rate 0.003, 600 full-batch steps. Because it only ever saw healthy snapshots, a damaged bearing's features do not fit the pattern and the rebuild error rises. That error goes through exactly the same peer contrast and six-in-a-row rule as the physics alarm, with a floor of 0.5, about 65 percent above the peers. Unlike the physics alarm, it looks at the joint pattern of all 16 features, so it reacts to peakiness changes before the energy grows.");
  // diagram
  const y0 = 1.75, h = 2.3, ax = 1.0, heights = [2.1, 1.6, 0.7, 1.6, 2.1], labels = ["16", "12", "4", "12", "16"];
  txt(s, "Encoder → bottleneck → decoder", { x: M, y: y0 - 0.15, w: 4.4, h: 0.35, fontSize: 16, bold: true, color: COL.teal, align: "center" });
  heights.forEach((bh, i) => {
    rect(s, { x: ax + i * 0.75, y: y0 + 0.3 + (h - bh) / 2, w: 0.48, h: bh, fill: { color: i === 2 ? COL.coral : COL.mid }, line: { color: i === 2 ? COL.coral : COL.mid } });
    txt(s, labels[i], { x: ax + i * 0.75 - 0.05, y: y0 + 0.35 + h, w: 0.58, h: 0.32, fontSize: 16, align: "center", color: COL.grey });
  });
  txt(s, "input: 16 features", { x: M, y: y0 + 2.95, w: 2.2, h: 0.3, fontSize: 14, color: COL.grey });
  txt(s, "output: rebuilt 16", { x: 2.85, y: y0 + 2.95, w: 2.2, h: 0.3, fontSize: 14, color: COL.grey, align: "right" });
  T(s, [
    ["Setting", "Value"],
    ["Layers", "16 → 12 → 4 → 12 → 16, tanh (524 weights, 3 KB)"],
    ["Training data", "Healthy window only: first 20% of each test, 4 bearings pooled"],
    ["Loss, optimiser", "Mean squared rebuild error; Adam, lr 0.003, 600 steps"],
    ["Anomaly score", "Rebuild error per snapshot"],
    ["Alarm rule", "Same peer contrast + 6 in a row; floor 0.5 (≈ 65% above peers)"],
  ], [2.0, 5.53], 1.6, { x: 5.2, w: 7.53, fs: 16 });
  box(s, { x: M, y: 5.3, w: CW, h: 1.1 });
  txt(s, [{ text: "Why it differs from the physics alarm: ", options: { bold: true, color: COL.teal } },
    { text: "it reads the joint pattern of all 16 features, so it reacts to peakiness changes before the energy grows." }],
  { x: M + 0.3, y: 5.3, w: CW - 0.6, h: 1.1, fontSize: 18, valign: "middle" });
  cite(s, "Autoencoder anomaly detection: Sakurada & Yairi, 2014");
}

// =====================================================================
// 9. Why these models
{
  const s = add("CONTENT", "Method", "We chose two label-free alarms because the data holds only four failures",
    "Why these two models and not something bigger? The key constraint is the data: 12 bearings, only 4 failures, and only one inner-race and one roller failure. A supervised classifier, a random forest or a CNN, needs labelled failures of each type. In Part I a supervised CNN could not name a fault type it had not seen. Remaining-life regression needs many run-to-failure histories; with four, its error was as wide as the warning itself. Foundation models are large and, used zero-shot, gave more false alarms. Both of our alarms need only healthy data, which every plant has in plenty. And they look at different signals, energy versus the shape of the feature pattern, so they tend to miss different bearings. That is the reason for using two.");
  T(s, [
    ["Option", "Needs", "Problem with 4 failures", "Decision"],
    ["Supervised classifier (RF, CNN)", "Labelled failures of each type", "1 inner, 1 roller example: can't learn them", { text: "Not used", options: { color: HEX.red, bold: true } }],
    ["RUL regression", "Many run-to-failure histories", "Error 17-59 h, as wide as the warning", { text: "Tried (appendix)", options: { color: HEX.red, bold: true } }],
    ["Foundation model, zero-shot", "38 M parameters, no training", "More false alarms than our 3 KB model", { text: "Tested (appendix)", options: { color: HEX.red, bold: true } }],
    ["Physics threshold (Stage A)", "Healthy data only", "None: no training, explainable", { text: "Alarm 1", options: { color: HEX.green, bold: true } }],
    ["Autoencoder", "Healthy data only", "None: tiny, learns the normal pattern", { text: "Alarm 2", options: { color: HEX.green, bold: true } }],
  ], [3.3, 3.0, 3.93, 1.9], 1.55, { fs: 17 });
  box(s, { x: M, y: 5.4, w: CW, h: 1.0, fill: { color: COL.teal }, line: { color: COL.teal } });
  txt(s, [{ text: "Why two: ", options: { bold: true, color: COL.coral } },
    { text: "they read different signals (energy vs. feature pattern), so they should fail on different bearings", options: { color: COL.white } }],
  { x: M + 0.3, y: 5.4, w: CW - 0.6, h: 1.0, fontSize: 20, valign: "middle" });
}

// =====================================================================
// 10. Complementary alarms
{
  const s = add("CONTENT", "Method", "Each alarm is late on a different bearing, so we act on the first one",
    "And that is what happens. This chart shows how many hours before the end each alarm fired, for the four failed bearings. The crew needs 24 hours, the dashed line. The physics alarm is too late on test 1 bearing 3, the inner race: 12 hours. Its energy rose late, but its peakiness rose early, which the autoencoder sees at 71 hours. The AI alarm never fires on test 3 bearing 3: its healthy neighbour bearing 4 also rose, so bearing 3 did not stand out enough. The physics alarm catches it at 53 hours. Each covers the other's gap. So the rule is: replace after whichever alarm fires first.");
  const cats = ["Test 1 B3\ninner race", "Test 1 B4\nroller", "Test 2 B1\nouter race", "Test 3 B3\nouter race"];
  s.addChart([
    { type: pres.charts.BAR, data: [
      { name: "Physics alarm (Stage A)", labels: cats, values: [12, 97, 70, 53] },
      { name: "AI alarm (autoencoder)", labels: cats, values: [71, 119, 54, 0] }],
      options: { barDir: "col", barGapWidthPct: 60, chartColors: [HEX.teal, HEX.mid] } },
    { type: pres.charts.LINE, data: [{ name: "Crew needs 24 h", labels: cats, values: [24, 24, 24, 24] }],
      options: { chartColors: [HEX.red], lineSize: 2, lineDataSymbol: "none", lineDash: "dash", showValue: false } },
  ], Object.assign(axis(), {
    x: M, y: 1.5, w: 7.9, h: 4.95, showLegend: true, legendPos: "t",
    showValue: true, dataLabelFontSize: 16, dataLabelColor: HEX.ink, dataLabelPosition: "outEnd",
    valAxisMinVal: 0, valAxisMaxVal: 140, valAxisMajorUnit: 20, showValAxisTitle: true, valAxisTitle: "Warning before failure (h)",
  }));
  const ry = 1.6;
  box(s, { x: 8.85, y: ry, w: 3.88, h: 1.5 });
  txt(s, [{ text: "Test 1 B3: ", options: { bold: true, color: COL.red } }, { text: "physics only 12 h early. Energy rose late; peakiness rose early (AI: 71 h)" }],
    { x: 9.05, y: ry + 0.12, w: 3.5, h: 1.3, fontSize: 17 });
  box(s, { x: 8.85, y: ry + 1.65, w: 3.88, h: 1.5 });
  txt(s, [{ text: "Test 3 B3: ", options: { bold: true, color: COL.red } }, { text: "AI never fires: healthy neighbour B4 rose too, so B3 did not stand out" }],
    { x: 9.05, y: ry + 1.77, w: 3.5, h: 1.3, fontSize: 17 });
  box(s, { x: 8.85, y: ry + 3.3, w: 3.88, h: 1.55, fill: { color: COL.teal }, line: { color: COL.teal } });
  txt(s, [{ text: "Our rule: ", options: { bold: true, color: COL.coral } }, { text: "replace after either alarm. Together they warn in time on all 4", options: { color: COL.white } }],
    { x: 9.05, y: ry + 3.45, w: 3.5, h: 1.3, fontSize: 18 });
}

// =====================================================================
// 11. Decision logic + work order
{
  const s = add("CONTENT", "Method", "The first alarm opens a work order automatically; the crew has 24 h",
    "This is the decision logic, the automation in Part II. Every 10 minutes both alarms are checked. If either fires and the bearing has no open work order, the system opens one immediately. The code fills in the asset, the fault type from Stage B, so the crew brings the right part, and a due time 24 hours later, our assumed lead time for parts and scheduling. A second alarm on the same bearing is only logged. Then each bearing ends in one of three outcomes. If it is replaced before it breaks, it was caught in time: a planned job, cost 1. If it breaks first, it is a breakdown, cost 10. If the bearing was healthy, the replacement was needless, cost 1. We use OR rather than AND because a miss costs ten times a false alarm.");
  const steps = [
    ["Every 10 min", "check both alarms"],
    ["Either fires?", "and no open order on this bearing"],
    ["Open work order", "asset · fault (Stage B) · due = now + 24 h"],
    ["Crew replaces", "by the due time"],
  ];
  const w = 2.7, gap = 0.4, y = 1.65;
  steps.forEach((st, i) => {
    const x = M + i * (w + gap), dark = i === 2;
    box(s, { x, y, w, h: 1.55, fill: { color: dark ? COL.teal : COL.tint }, line: { color: dark ? COL.teal : COL.tint } });
    txt(s, st[0], { x: x + 0.2, y: y + 0.15, w: w - 0.4, h: 0.45, fontSize: 20, bold: true, color: dark ? COL.coral : COL.teal });
    txt(s, st[1], { x: x + 0.2, y: y + 0.65, w: w - 0.4, h: 0.8, fontSize: 16, color: dark ? COL.white : COL.ink });
    if (i < 3) chev(s, x + w + 0.06, y + 0.57);
  });
  txt(s, "Outcome of each bearing", { x: M, y: 3.5, w: 6, h: 0.4, fontSize: 18, bold: true, color: COL.teal });
  T(s, [
    ["Bearing", "Replaced before it breaks?", "Outcome", "Cost"],
    ["Failing", "Yes (alarm ≥ 24 h before failure)", { text: "Caught in time", options: { color: HEX.green, bold: true } }, "1"],
    ["Failing", "No (no alarm, or < 24 h)", { text: "Breakdown", options: { color: HEX.red, bold: true } }, "10"],
    ["Healthy", "Replaced anyway (false alarm)", { text: "Needless replacement", options: { color: HEX.grey, bold: true } }, "1"],
  ], [1.4, 3.6, 2.5, 0.9], 3.95, { w: 8.4, fs: 17 });
  box(s, { x: 9.35, y: 3.95, w: 3.38, h: 2.45 });
  txt(s, [{ text: "Why OR, not AND? ", options: { bold: true, color: COL.teal, breakLine: true } },
    { text: "A miss costs 10, a false alarm costs 1. Waiting for both alarms would turn 2 catches into breakdowns." }],
  { x: 9.55, y: 4.1, w: 3.0, h: 2.2, fontSize: 17 });
}

// =====================================================================
// 12. Cost model
{
  const s = add("CONTENT", "Method", "Every strategy is scored by one number: cost per 1,000 operating hours",
    "Now the cost model. We treat each bearing as one renewal cycle: it starts new and ends when it is replaced or breaks. The standard renewal-reward estimate of the long-run cost rate is total cost divided by total hours run, which we report per 1,000 hours. Each strategy only changes how a cycle ends. Reactive: every failing bearing breaks, cost 10, after its full life. Preventive, also called age replacement: replace at T hours, cost 1; if it fails before T, cost 10. We search T from 24 to 1,100 hours and keep the best, with hindsight, which flatters preventive. Condition-based: replace at the alarm plus the lead time, cost 1, unless it fails first. Oracle: replace each failing bearing exactly at its end, the lowest possible cost. Why cost and not accuracy: a miss and a false alarm have different prices, and replacing too early is penalised because those hours never run.");
  box(s, { x: M, y: 1.6, w: CW, h: 0.95, fill: { color: COL.white }, line: { color: COL.teal, width: 1.5 } });
  txt(s, [{ text: "Cost rate = 1,000 × Σ cost  ÷  Σ hours run", options: { bold: true, color: COL.teal } },
    { text: "     (renewal-reward: each bearing is one cycle)", options: { color: COL.grey, fontSize: 18 } }],
  { x: M + 0.3, y: 1.6, w: CW - 0.6, h: 0.95, fontSize: 24, valign: "middle" });
  T(s, [
    ["Strategy", "How a bearing's cycle ends", "Cost", "Hours counted"],
    ["Reactive", "Runs until it breaks", "10 if it fails", "Full life"],
    ["Preventive (age T)", "Replaced at T; breaks if life < T", "1, or 10", "T, or life"],
    ["Condition-based", "Replaced at alarm + 24 h; breaks if it fails first", "1, or 10", "Alarm + 24 h, or life"],
    ["Oracle", "Replaced just before failure", "1 if it fails", "Full life"],
  ], [2.6, 5.2, 1.9, 2.43], 2.8, { fs: 17 });
  txt(s, bullets([
    "Planned job = 1, breakdown = 10, crew lead = 24 h (all varied later)",
    "Preventive T searched over 24-1,100 h, best kept with hindsight (optimistic)",
    "Why not accuracy: a miss and a false alarm have different prices; early replacement wastes hours",
  ]), { x: M, y: 5.0, w: CW, h: 1.5, fontSize: 18, paraSpaceAfter: 4 });
  cite(s, "Renewal-reward cost rate, age replacement: Jardine et al., 2006");
}

// =====================================================================
// 13. Worked example
{
  const s = add("CONTENT", "Method", "Worked example: our rule costs 6 units over 7,337 hours, or 0.82 per 1,000 h",
    "Here is the calculation for our rule, bearing by bearing, so you can check it. Six bearings never alarmed and were healthy: they cost nothing and count their full hours. The four failing bearings were each caught in time: cost 1 each, and their hours stop at the replacement, for example test 2 bearing 1 at hour 118 instead of 164. Two healthy bearings had a physics false alarm, test 2 bearing 4 and test 3 bearing 4: cost 1 each. Total: 6 cost units over 7,337 bearing-hours, which is 0.82 per 1,000 hours. Reactive, for comparison: four breakdowns, 40 units over 8,257 hours, 4.84.");
  const rows = [
    ["1", "B1, B2", "healthy", "none", "-", "0", "1,655"],
    ["1", "B3", "inner race", "AI · 71 h before end", "caught", "1", "781"],
    ["1", "B4", "roller", "AI · 119 h", "caught", "1", "733"],
    ["2", "B1", "outer race", "physics · 70 h", "caught", "1", "118"],
    ["2", "B2, B3", "healthy", "none", "-", "0", "327"],
    ["2", "B4", "healthy", "physics · 4 h", "needless", "1", "164"],
    ["3", "B1, B2", "healthy", "none", "-", "0", "2,146"],
    ["3", "B3", "outer race", "physics · 53 h", "caught", "1", "1,044"],
    ["3", "B4", "healthy", "physics · 728 h", "needless", "1", "369"],
  ];
  const col = { caught: HEX.green, needless: HEX.grey };
  T(s, [["Test", "Bearing", "Truth", "First alarm", "Outcome", "Cost", "Hours"],
    ...rows.map((r) => r.map((c, j) => (j === 4 && col[c] ? { text: c, options: { color: col[c], bold: true } } : c))),
    [{ text: "Total", options: { bold: true } }, "12", "", "", "", { text: "6", options: { bold: true } }, { text: "7,337", options: { bold: true } }]],
  [0.7, 1.15, 1.5, 2.6, 1.25, 0.8, 1.0], 1.5, { w: 9.0, fs: 15 });
  box(s, { x: 9.95, y: 1.5, w: 2.78, h: 2.3, fill: { color: COL.teal }, line: { color: COL.teal } });
  txt(s, [{ text: "6 ÷ 7,337 h × 1,000", options: { breakLine: true, color: COL.white, fontSize: 18 } },
    { text: "= 0.82", options: { bold: true, color: COL.coral, fontSize: 40 } }],
  { x: 10.15, y: 1.65, w: 2.4, h: 2.0, valign: "middle" });
  box(s, { x: 9.95, y: 4.0, w: 2.78, h: 2.3 });
  txt(s, [{ text: "Reactive", options: { bold: true, color: COL.teal, breakLine: true } },
    { text: "4 × 10 = 40 over 8,257 h", options: { breakLine: true, fontSize: 15 } },
    { text: "= 4.84", options: { bold: true, color: COL.red, fontSize: 36 } }],
  { x: 10.15, y: 4.15, w: 2.4, h: 2.0, fontSize: 18, valign: "middle" });
}

// =====================================================================
// 14. Replay of test 2 with the work order
pres.addSection({ title: "Results" });
{
  const s = add("CONTENT", "Results", "Test 2: the alarm opens a work order 70 h before the bearing breaks",
    "Here is one bearing replayed with the rule, to make the work order concrete. The line is the vibration energy of test 2, bearing 1. Around hour 90 it starts to rise. At hour 94 the physics alarm fires and the system opens work order WO-T2-B1: work order, test 2, bearing 1. Stage B fills in the fault: outer race. It is due at hour 118. The AI alarm agrees at 110, which is just logged. At 118 the bearing is replaced. The grey dashed line is what really happened in the test: nobody replaced it, and it broke at hour 164. So we pay 1 instead of 10.");
  const R = JSON.parse(fs.readFileSync(__dirname + "/replay_small.json"));
  const marks = [94, 110, 118, 163.8];
  const X = [...R.live.x, ...R.old.x];
  marks.forEach((m) => X.push(m, m));
  const nL = R.live.x.length, nO = R.old.x.length, N = X.length;
  const colv = (start, ys) => { const v = new Array(N).fill(null); ys.forEach((y, i) => (v[start + i] = y)); return v; };
  const YTOP = 0.55;
  const series = [{ name: "X", values: X }, { name: "Bearing 1 vibration (RMS)", values: colv(0, R.live.y) },
    { name: "Real test: never replaced", values: colv(nL, R.old.y) }];
  marks.forEach((m, i) => series.push({ name: "mark " + i, values: colv(nL + nO + 2 * i, [0, YTOP]) }));
  const cx = M, cy = 1.85, cw = 8.3, ch = 4.45, PL = { x: 0.1, y: 0.04, w: 0.86, h: 0.8 };
  s.addChart(pres.charts.SCATTER, series, Object.assign(axis(), {
    x: cx, y: cy, w: cw, h: ch, layout: PL,
    chartColors: [HEX.teal, HEX.grey, HEX.coral, HEX.mid, HEX.green, HEX.red],
    lineSize: 2.5, lineDataSymbol: "none", showLegend: false, displayBlanksAs: "gap",
    valAxisMinVal: 0, valAxisMaxVal: YTOP, valAxisMajorUnit: 0.1, valAxisLabelFormatCode: "0.0",
    catAxisMinVal: 0, catAxisMaxVal: 168, catAxisMajorUnit: 24,
    showValAxisTitle: true, valAxisTitle: "Vibration energy (RMS, g)",
    showCatAxisTitle: true, catAxisTitle: "Hours since test 2 started",
  }));
  const xAt = (h) => cx + cw * (PL.x + PL.w * (h / 168));
  [[94, "94 alarm", COL.coral, -0.95], [110, "110 AI agrees", COL.mid, -0.35], [118, "118 replaced", COL.green, 0.05], [163.8, "164 breaks", COL.red, -0.9]]
    .forEach((l, i) => txt(s, l[1], { x: xAt(l[0]) + l[3], y: 1.4 + (i % 2) * 0.33, w: 1.6, h: 0.32, fontSize: 16, bold: true, color: l[2] }));
  const wx = 9.2, wy = 1.5, ww = 3.53;
  box(s, { x: wx, y: wy, w: ww, h: 4.85, fill: { color: COL.white }, line: { color: COL.teal, width: 1.5 } });
  txt(s, "Work order WO-T2-B1", { x: wx + 0.25, y: wy + 0.2, w: ww - 0.5, h: 0.45, fontSize: 20, bold: true, color: COL.teal });
  txt(s, "= Work Order · Test 2 · Bearing 1", { x: wx + 0.25, y: wy + 0.65, w: ww - 0.5, h: 0.35, fontSize: 16, color: COL.grey });
  [["Opened", "hour 94, by the alarm"], ["Fault", "outer race (Stage B)"], ["Due", "hour 118 (crew needs 24 h)"], ["Result", "replaced in time: cost 1, not 10"]]
    .forEach((r, i) => {
      const y = wy + 1.15 + i * 0.9;
      txt(s, r[0], { x: wx + 0.25, y, w: ww - 0.5, h: 0.3, fontSize: 16, bold: true, color: COL.coral });
      txt(s, r[1], { x: wx + 0.25, y: y + 0.3, w: ww - 0.5, h: 0.55, fontSize: 16 });
    });
  txt(s, "Grey dashed: the real test, where nobody replaced the bearing. All 12 bearings: 6 work orders, 4 in time, 2 needless.",
    { x: M, y: 6.45, w: CW, h: 0.45, fontSize: 14, color: COL.grey });
}

// =====================================================================
// 15. Confusion matrices
{
  const s = add("CONTENT", "Results", "Confusion matrices: only the combined rule catches all 4 failures in time",
    "Here are the alarms as confusion matrices over the 12 bearings. Rows are the truth: failed or healthy. Columns are the decision: replaced in time, meaning an alarm at least 24 hours before failure, or not. For the physics alarm: 3 caught, 1 too late, 2 false alarms on healthy bearings, 6 correctly left alone. The AI alarm: 3 caught, 1 missed, and no false alarms at all. Combined with OR: all 4 caught, no misses, and the 2 false alarms of the physics alarm. Recall goes to 100 percent, at the price of 2 false alarms. Since a miss costs 10 and a false alarm costs 1, that trade is worth it: 2 extra units instead of 10.");
  const mats = [
    ["Physics alarm", [3, 1, 2, 6]],
    ["AI alarm", [3, 1, 0, 8]],
    ["Physics OR AI (our rule)", [4, 0, 2, 6]],
  ];
  const cell = 1.15, top = 2.3;
  mats.forEach((m, k) => {
    const x0 = M + 1.05 + k * 4.05;
    txt(s, m[0], { x: x0 - 1.0, y: 1.5, w: 3.4, h: 0.4, fontSize: 20, bold: true, color: k === 2 ? COL.coral : COL.teal, align: "center" });
    txt(s, "Alarm in time", { x: x0, y: top - 0.38, w: cell, h: 0.32, fontSize: 13, color: COL.grey, align: "center" });
    txt(s, "No / too late", { x: x0 + cell, y: top - 0.38, w: cell, h: 0.32, fontSize: 13, color: COL.grey, align: "center" });
    txt(s, "Failed (4)", { x: x0 - 1.05, y: top, w: 1.0, h: cell, fontSize: 14, color: COL.grey, valign: "middle", align: "right" });
    txt(s, "Healthy (8)", { x: x0 - 1.05, y: top + cell, w: 1.0, h: cell, fontSize: 14, color: COL.grey, valign: "middle", align: "right" });
    const lab = ["caught", "breakdown", "needless", "left alone"];
    const fills = [HEX.green, HEX.red, HEX.grey, HEX.tint];
    m[1].forEach((v, i) => {
      const cxx = x0 + (i % 2) * cell, cyy = top + Math.floor(i / 2) * cell;
      const on = v > 0 && i !== 3;
      rect(s, { x: cxx, y: cyy, w: cell, h: cell, fill: { color: on ? fills[i] : HEX.tint }, line: { color: HEX.white, width: 2 } });
      txt(s, [{ text: String(v), options: { fontSize: 32, bold: true, breakLine: true } }, { text: lab[i], options: { fontSize: 13 } }],
        { x: cxx, y: cyy, w: cell, h: cell, align: "center", valign: "middle", color: on ? COL.white : COL.ink });
    });
    const rec = Math.round((m[1][0] / 4) * 100);
    txt(s, [{ text: `Recall ${rec}%`, options: { bold: true, breakLine: true } }, { text: `False alarms ${m[1][2]} of 8` }],
      { x: x0 - 0.6, y: top + 2 * cell + 0.15, w: 2 * cell + 1.2, h: 0.7, fontSize: 17, align: "center", color: k === 2 ? COL.coral : COL.ink });
  });
  box(s, { x: M, y: 5.6, w: CW, h: 0.85, fill: { color: COL.teal }, line: { color: COL.teal } });
  txt(s, [{ text: "Trade-off: ", options: { bold: true, color: COL.coral } },
    { text: "+2 false alarms (2 × 1 unit) buy back the missed failure (10 units)", options: { color: COL.white } }],
  { x: M + 0.3, y: 5.6, w: CW - 0.6, h: 0.85, fontSize: 20, valign: "middle" });
  cite(s, "\"In time\" = alarm at least 24 h before failure. A healthy bearing counts as a false alarm if any alarm fires.");
}

// =====================================================================
// 16. Main result
{
  const s = add("CONTENT", "Results", "Acting on either alarm cuts cost 6× with zero breakdowns",
    "Here is the result for all strategies, with 24 hours lead time and a breakdown costing 10. Run-to-failure costs 4.84 per 1,000 hours, with four breakdowns. The best fixed interval, every 824 hours, picked with hindsight, costs 2.48: one breakdown and five needless replacements. Each alarm alone misses one failure: 2.03 and 1.61. Acting on either alarm catches all four, no breakdowns, 0.82: about six times cheaper than run-to-failure. The oracle that knows the future would pay 0.48. The gap between us and the oracle is exactly the two false alarms.");
  const cats = ["Reactive (run to failure)", "Preventive, every 824 h*", "Physics alarm only", "AI alarm only", "Physics OR AI (our rule)", "Oracle (knows the future)"];
  s.addChart(pres.charts.BAR, [{ name: "Cost per 1,000 h", labels: cats, values: [4.84, 2.48, 2.03, 1.61, 0.82, 0.48] }], Object.assign(axis(), {
    x: M, y: 1.5, w: 7.9, h: 4.9, barDir: "bar", catAxisOrientation: "maxMin", barGapWidthPct: 45,
    chartColors: [HEX.grey, HEX.grey, HEX.mid, HEX.mid, HEX.coral, HEX.pale],
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 18, dataLabelColor: HEX.ink, dataLabelFormatCode: "0.00",
    valAxisMinVal: 0, valAxisMaxVal: 5.5, valAxisMajorUnit: 1, valAxisHidden: true, valGridLine: { style: "none" },
    showLegend: false, showTitle: true, title: "Cost per 1,000 h (breakdown = 10, planned = 1)", titleFontSize: 16, titleColor: HEX.ink, titleFontFace: "+mn-lt",
  }));
  T(s, [["Strategy", "Caught", "Break-downs", "Need-less"],
    ["Reactive", "0", "4", "0"], ["Preventive*", "3", "1", "5"], ["Physics", "3", "1", "2"], ["AI", "3", "1", "0"],
    [{ text: "Either", options: { bold: true, color: HEX.coral } }, { text: "4", options: { bold: true } }, { text: "0", options: { bold: true } }, "2"]],
  [1.2, 0.95, 0.88, 0.85], 1.6, { x: 8.85, w: 3.88, fs: 15 });
  txt(s, "Gap to the oracle (0.82 vs 0.48) = the 2 false alarms", { x: 8.85, y: 4.55, w: 3.88, h: 0.9, fontSize: 18, bold: true, color: COL.teal });
  cite(s, "* Best fixed interval, chosen with hindsight, so optimistic. Lead time 24 h.");
}

// =====================================================================
// 17. Sensitivity
{
  const s = add("CONTENT", "Results", "Our rule beats run-to-failure once a breakdown costs over 2× a repair",
    "Is the factor of 10 important? Here we change it. Each group of bars is one breakdown cost: 2, 5, 10 and 20 times a planned replacement. Run-to-failure gets more expensive as breakdowns get more expensive, because it has four of them. Our rule stays flat at 0.82, because it has no breakdowns to pay for. It is already cheaper than run-to-failure at 2 times. If breakdowns are cheap, below about 3.6 times, the AI alarm alone is slightly cheaper, because it has no false alarms. Above that, acting on either alarm wins. In a real plant a breakdown usually costs far more than twice a planned job.");
  const cats = ["2×", "5×", "10×", "20×"];
  s.addChart(pres.charts.BAR, [
    { name: "Reactive (run to failure)", labels: cats, values: [0.97, 2.42, 4.84, 9.69] },
    { name: "AI alarm only", labels: cats, values: [0.62, 0.99, 1.61, 2.84] },
    { name: "Physics OR AI (our rule)", labels: cats, values: [0.82, 0.82, 0.82, 0.82] },
  ], Object.assign(axis(), {
    x: M, y: 1.5, w: 8.2, h: 4.9, barDir: "col", barGapWidthPct: 55, barOverlapPct: 0,
    chartColors: [HEX.grey, HEX.mid, HEX.coral], showLegend: true, legendPos: "t",
    showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 14, dataLabelColor: HEX.ink, dataLabelFormatCode: "0.0",
    valAxisMinVal: 0, valAxisMaxVal: 10, valAxisMajorUnit: 2, showValAxisTitle: true, valAxisTitle: "Cost per 1,000 h",
    showCatAxisTitle: true, catAxisTitle: "Breakdown cost ÷ planned replacement cost",
  }));
  [["Our rule stays flat:", "no breakdowns to pay for"], ["Run-to-failure grows:", "4 breakdowns, each paid at full price"],
    ["Below ~3.6×:", "AI alone is slightly cheaper (no false alarms)"]].forEach((p, i) => {
    const y = 1.6 + i * 1.5;
    box(s, { x: 9.15, y, w: 3.58, h: 1.3 });
    txt(s, [{ text: p[0] + " ", options: { bold: true, color: COL.teal } }, { text: p[1] }], { x: 9.35, y: y + 0.12, w: 3.2, h: 1.1, fontSize: 18 });
  });
}

// =====================================================================
// 18. Fault-type confusion matrix
{
  const s = add("CONTENT", "Results", "Stage B names the right part on all 4 failing bearings",
    "The work order also carries the fault type from Stage B, so the crew knows what to replace. This matrix covers the six bearings that got a work order. Rows are the truth, columns what Stage B wrote in the order. All four failing bearings are named correctly: two outer race, one inner race, one roller. The two false alarms are healthy bearings. Test 2 bearing 4 was written as outer race: it sits on the same shaft as the failing outer-race bearing 1, and that signature reaches every sensor. Test 3 bearing 4 got unspecified, meaning no fault rhythm was strong enough to name. In practice an unspecified order is a hint to inspect before replacing.");
  const cols = ["Outer race", "Inner race", "Roller", "Unspecified"];
  const rowsM = [["Outer race (2)", [2, 0, 0, 0]], ["Inner race (1)", [0, 1, 0, 0]], ["Roller (1)", [0, 0, 1, 0]], ["Healthy (2)", [1, 0, 0, 1]]];
  const x0 = 2.75, y0 = 2.1, cw = 1.3, chh = 0.85;
  txt(s, "Stage B verdict in the work order →", { x: x0, y: 1.5, w: 4 * cw, h: 0.3, fontSize: 15, color: COL.grey, align: "center" });
  cols.forEach((c, j) => txt(s, c, { x: x0 + j * cw, y: y0 - 0.32, w: cw, h: 0.3, fontSize: 15, bold: true, color: COL.teal, align: "center" }));
  rowsM.forEach((r, i) => {
    txt(s, r[0], { x: M, y: y0 + i * chh, w: 2.05, h: chh, fontSize: 16, bold: true, color: COL.teal, valign: "middle", align: "right" });
    r[1].forEach((v, j) => {
      const diag = i === j && i < 3, wrong = v > 0 && !diag;
      const fill = v === 0 ? HEX.tint : diag ? HEX.green : HEX.grey;
      rect(s, { x: x0 + j * cw, y: y0 + i * chh, w: cw, h: chh, fill: { color: fill }, line: { color: HEX.white, width: 2 } });
      txt(s, String(v), { x: x0 + j * cw, y: y0 + i * chh, w: cw, h: chh, fontSize: 26, bold: v > 0, align: "center", valign: "middle", color: v > 0 ? COL.white : COL.grey });
    });
  });
  txt(s, "True condition (bearings with a work order)", { x: M, y: y0 + 4 * chh + 0.1, w: 7.4, h: 0.3, fontSize: 14, color: COL.grey });
  const pts = [
    ["4 / 4", "failing bearings named correctly", COL.green],
    ["T2 B4", "healthy, written as outer race: B1's outer-race signature on the same shaft", COL.grey],
    ["T3 B4", "healthy, unspecified: no rhythm strong enough → inspect first", COL.grey],
  ];
  pts.forEach((p, i) => {
    const y = 1.6 + i * 1.45;
    box(s, { x: 8.55, y, w: 4.18, h: 1.25 });
    txt(s, p[0], { x: 8.75, y, w: 1.3, h: 1.25, fontSize: 22, bold: true, color: p[2], valign: "middle" });
    txt(s, p[1], { x: 10.1, y, w: 2.5, h: 1.25, fontSize: 15, valign: "middle" });
  });
  cite(s, "Stage B: envelope spectrum at the fault frequencies (Part I). Envelope analysis: Randall & Antoni, 2011");
}

// =====================================================================
// 19. Conclusion
pres.addSection({ title: "Conclusion" });
{
  const s = add("CONTENT", "Conclusion", "Use both alarms, and replace the bearing within two days of the first one",
    "To conclude. Part I gave us two label-free alarms that fail on different bearings. Acting on either one gives no breakdowns and is about six times cheaper than running to failure. That holds when a breakdown costs more than twice a planned job, and when the crew replaces the bearing within about two days; with 72 hours, most failures are missed. The work order is opened automatically and Stage B tells the crew what to replace. The limits: one lab rig, four failures, assumed costs, thresholds chosen on the same bearings. It is a case study, not a validated accuracy. The backup slides cover robustness, lead time, remaining-life prediction, foundation models and running on a Raspberry Pi.");
  [["0", "breakdowns when acting on either alarm"], ["6×", "cheaper than run-to-failure"],
    ["> 2×", "breakdown cost at which it beats reactive"], ["≤ 48 h", "for the crew to replace the bearing"]].forEach((t, i) => {
    const x = M + i * 3.1, w = 2.85, y = 1.6;
    box(s, { x, y, w, h: 2.4 });
    txt(s, t[0], { x: x + 0.25, y: y + 0.2, w: w - 0.5, h: 1.0, fontSize: 48, bold: true, color: COL.coral, valign: "middle" });
    txt(s, t[1], { x: x + 0.25, y: y + 1.3, w: w - 0.5, h: 1.0, fontSize: 18 });
  });
  txt(s, [
    { text: "Why it works: ", options: { bold: true, color: COL.teal } },
    { text: "two label-free alarms reading different signals; OR rule because a miss costs 10× a false alarm", options: { breakLine: true } },
    { text: "Limits: ", options: { bold: true, color: COL.teal } },
    { text: "one lab rig, 4 failures, assumed costs, in-sample thresholds: a case study", options: { breakLine: true } },
    { text: "Tried, no gain at 4 failures: ", options: { bold: true, color: COL.teal } },
    { text: "remaining-life prediction, foundation models (backup slides)" },
  ], { x: M, y: 4.3, w: CW, h: 1.8, fontSize: 19, paraSpaceAfter: 8 });
  txt(s, "Questions and feedback welcome · Adrian F. Jotham, Han Yuxin, Gifar A. Haryadi", { x: M, y: 6.35, w: CW, h: 0.4, fontSize: 16, color: COL.grey });
}

// =====================================================================
// 20. References
{
  const s = add("CONTENT", "Conclusion", "References", "Sources cited in this deck. All numbers come from our own pipeline on the IMS dataset.");
  const refs = [
    "Jardine, A.K.S., Lin, D., Banjevic, D. (2006). A review on machinery diagnostics and prognostics implementing condition-based maintenance. Mech. Syst. Signal Process. 20(7), 1483-1510.",
    "Randall, R.B., Antoni, J. (2011). Rolling element bearing diagnostics: a tutorial. Mech. Syst. Signal Process. 25(2), 485-520.",
    "Sakurada, M., Yairi, T. (2014). Anomaly detection using autoencoders with nonlinear dimensionality reduction. Proc. MLSDA 2014, 4-11.",
    "Lei, Y., et al. (2018). Machinery health prognostics: a systematic review from data acquisition to RUL prediction. Mech. Syst. Signal Process. 104, 799-834.",
    "Qiu, H., Lee, J., Lin, J., Yu, G. (2006). Wavelet filter-based weak signature detection method and its application on rolling element bearing prognostics. J. Sound Vib. 289(4-5), 1066-1090.",
    "IMS bearing dataset. NASA Prognostics Data Repository (Center for Intelligent Maintenance Systems, Univ. of Cincinnati).",
    "Goswami, M., et al. (2024). MOMENT: a family of open time-series foundation models. Proc. ICML 2024.",
    "Eldele, E., Ragab, M., et al. (2025). UniFault: a fault diagnosis foundation model from bearing data. arXiv:2504.01373.",
    "Ansari, A.F., et al. (2025). Chronos-2: from univariate to universal forecasting. arXiv:2510.15821.",
    "Arciniegas, S., Rivero, D., Piñan, J., Diaz, E., Rivas, F. (2025). IoT device for detecting abnormal vibrations in motors using TinyML. Discover Internet of Things 5, 41.",
  ];
  txt(s, refs.map((r, i) => ({ text: r, options: { breakLine: i < refs.length - 1, paraSpaceAfter: 6 } })),
    { x: M, y: 1.5, w: CW, h: 5.3, fontSize: 14 });
}

// =====================================================================
// Appendix (hidden)
pres.addSection({ title: "Appendix (hidden)" });
const appx = (title, notes) => { const s = add("APPENDIX", "Appendix (hidden)", title, notes, "Appendix"); s.hidden = !process.env.SHOW_HIDDEN; return s; };
{
  const s = appx("A · No breakdowns in any alarm-threshold setting we tried",
    "Backup for: did you tune the thresholds on the same bearings? Yes, so we moved them. 27 combinations gave 9 distinct outcomes, because the AI threshold changed nothing. Acting on either alarm had no breakdowns in all 9.");
  T(s, [
    ["Check", "What we found"],
    ["Alarm thresholds (27 combinations, 9 distinct)", "Either alarm: no breakdowns in all 9, cost 0.81-1.08. Physics alone: only 3 of 9"],
    ["Leave one test out", "Either alarm still beats reactive (3.9-7.6) and preventive (1.2-3.5)"],
    ["False alarms cost more", "From 4× a planned job, AI alone is cheapest (at 5×: 1.61 vs 1.91)"],
    ["Running vs calendar hours", "Test 1 paused overnight; using running hours, same ranking (1.11 vs reactive 6.41)"],
    ["Cross-talk (test 1 B3 alarm from B4?)", "Mostly no: driven by B3's own peakiness features"],
  ], [4.4, 7.73], 1.55);
}
{
  const s = appx("B · The crew must replace the bearing within about 48 hours",
    "Backup for: how fast must the crew act? Breakdowns by lead time. With either alarm, no breakdowns up to 48 hours. At 72 hours, three of four fail first, because the alarms come 53 to 119 hours before failure.");
  T(s, [
    ["Breakdowns (of 4) by lead time", "4 h", "8 h", "12 h", "24 h", "48 h", "72 h"],
    ["Physics alarm", 0, 0, 1, 1, 1, 3],
    ["AI alarm", 1, 1, 1, 1, 1, 3],
    ["Physics OR AI (our rule)", 0, 0, 0, 0, 0, 3],
  ], [4.13, 1.33, 1.33, 1.33, 1.33, 1.33, 1.35], 1.55);
  txt(s, "Lead time = hours from the alarm to the replacement. Default thresholds. Alarms come 53-119 h before failure, so 72 h is too slow for every rule.",
    { x: M, y: 4.0, w: CW, h: 0.9, fontSize: 18, color: COL.grey });
}
{
  const s = appx("C · Predicting the hours left (RUL) did not beat acting at the alarm",
    "Backup for: why not predict remaining useful life? We tried twice. Gradient boosting with a conformal safety margin: the margin was 17 to 59 hours, as wide as the lead time, so it never caught more than acting at the alarm. And the zero-shot forecaster Chronos-2 predicted flat vibration when it actually rose fast. With four failures there is too little to learn from.");
  [
    ["RUL model + conformal margin", "17-59 h", "safety margin: as wide as the lead time", ["Never catches more than acting at the alarm", "Bearings lasted 12-97 h after the alarm: too spread to learn from 3 examples"]],
    ["Chronos-2 forecaster (zero-shot)", "56 vs 25 h", "RUL error vs gradient boosting (test 2 B1)", ["Forecasts flat vibration; it really rose fast", "Forecasters continue the trend; a failure breaks it"]],
  ].forEach((c, i) => {
    const x = M + i * 6.2, w = 5.93, y = 1.55;
    box(s, { x, y, w, h: 4.6 });
    txt(s, c[0], { x: x + 0.3, y: y + 0.25, w: w - 0.6, h: 0.45, fontSize: 20, bold: true, color: COL.teal });
    txt(s, c[1], { x: x + 0.3, y: y + 0.85, w: w - 0.6, h: 0.8, fontSize: 40, bold: true, color: COL.coral });
    txt(s, c[2], { x: x + 0.3, y: y + 1.65, w: w - 0.6, h: 0.4, fontSize: 16, color: COL.grey });
    txt(s, bullets(c[3]), { x: x + 0.3, y: y + 2.3, w: w - 0.6, h: 2.1, fontSize: 18, paraSpaceAfter: 6 });
  });
  cite(s, "RUL review: Lei et al., 2018 · Chronos-2: Ansari et al., 2025");
}
{
  const s = appx("D · Foundation models were no better than our 3 KB autoencoder",
    "Backup for: did you try foundation models? Yes, two, used zero-shot with the same alarm rule and cost model. Neither beats the 524-weight autoencoder on cost. MOMENT flags 5 of 8 healthy bearings. UniFault probably saw IMS data in pretraining, so its result is optimistic.");
  T(s, [
    ["Alarm", "Model size", "Caught", "Breakdowns", "False alarms", "Cost / 1,000 h"],
    ["AI alarm (our autoencoder)", "524 weights, 3 KB", 3, 1, 0, "1.61"],
    ["Physics alarm", "no training", 3, 1, 2, "2.03"],
    ["MOMENT-1-small, zero-shot", "38 M parameters", 3, 1, 5, "3.01"],
    ["UniFault-Tiny, zero-shot*", "0.8 M parameters", 3, 1, 2, "2.16"],
    ["Physics OR AI (our rule)", "both above", 4, 0, 2, "0.82"],
  ], [3.6, 2.4, 1.3, 1.6, 1.6, 1.63], 1.55);
  txt(s, "Same alarm rule and cost model, no retraining. *IMS is one of UniFault's datasets: probably seen in pretraining, so optimistic.",
    { x: M, y: 4.75, w: CW, h: 0.8, fontSize: 18, color: COL.grey });
  cite(s, "MOMENT: Goswami et al., 2024 · UniFault: Eldele et al., 2025");
}
{
  const s = appx("E · The AI alarm runs on a Raspberry Pi 5 in 34 ms per snapshot",
    "Backup for: can this run in a factory? The autoencoder exports to a 3 KB ONNX file and gives identical alarm times. The full path, from reading the raw file to the alarm score, takes 34 milliseconds per snapshot on a Raspberry Pi 5. A snapshot arrives every 10 minutes, so this is far fast enough.");
  [["3 KB", "ONNX model, 524 weights"], ["Identical", "alarm times to the desktop model"], ["34 ms", "per snapshot on a Raspberry Pi 5 (desktop 14 ms)"], ["10 min", "between snapshots: ample margin"]].forEach((t, i) => {
    const x = M + i * 3.1, w = 2.85, y = 1.6;
    box(s, { x, y, w, h: 2.6 });
    txt(s, t[0], { x: x + 0.25, y: y + 0.25, w: w - 0.5, h: 1.0, fontSize: 40, bold: true, color: COL.teal, valign: "middle" });
    txt(s, t[1], { x: x + 0.25, y: y + 1.35, w: w - 0.5, h: 1.1, fontSize: 18 });
  });
  txt(s, "Time includes reading the raw file, computing the 16 features and running the model, for 4 sensors.", { x: M, y: 4.55, w: CW, h: 0.6, fontSize: 18, color: COL.grey });
  cite(s, "Edge monitoring with TinyML: Arciniegas et al., 2025");
}

// ---------- write, post-process the scatter chart, apply theme ----------
(async () => {
  await pres.writeFile({ fileName: OUT });
  const zip = await JSZip.loadAsync(fs.readFileSync(OUT));
  for (const f of Object.keys(zip.files).filter((f) => /ppt\/charts\/chart\d+\.xml$/.test(f))) {
    let x = await zip.file(f).async("string");
    if (!x.includes("<c:scatterChart>")) continue;
    x = x.replace(/<c:pt idx="\d+"><c:v><\/c:v><\/c:pt>/g, ""); // blanks -> missing points (gaps)
    x = x.replace(/<c:valAx>[\s\S]*?<\/c:valAx>/g, (ax) => // hours axis: whole numbers
      ax.includes('<c:axPos val="b"/>') ? ax.replace(/formatCode="0\.0"/, 'formatCode="0"') : ax);
    x = x.replace(/<c:ser>[\s\S]*?<\/c:ser>/g, (ser) =>
      /Real test|mark /.test(ser) ? ser.replace(/<a:prstDash val="solid"\/>/g, '<a:prstDash val="dash"/>') : ser);
    zip.file(f, x);
  }
  fs.writeFileSync(OUT, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})();
