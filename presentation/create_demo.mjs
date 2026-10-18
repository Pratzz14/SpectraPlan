import fs from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { Presentation, PresentationFile } from "@oai/artifact-tool";

const workspaceDir = "C:/Users/prati/OneDrive/Desktop/SpectraPlan";
const skillDir = "C:/Users/prati/.codex/plugins/cache/openai-primary-runtime/presentations/26.1015.12040/skills/presentations";
const taskWorkspace = workspaceDir;
const buildDir = path.join(workspaceDir, "presentation/.build");
const outputDir = path.join(workspaceDir, "presentation/output");
const finalPath = path.join(outputDir, "spectraplan-demo.pptx");
const fontFamily = "Aptos";
const C = { ink: "slate-950", muted: "slate-600", line: "slate-200", surface: "white", accent: "indigo-600", accentSoft: "indigo-50", warm: "amber-50" };

await fs.mkdir(buildDir, { recursive: true });
await fs.mkdir(outputDir, { recursive: true });

const presentation = Presentation.create({ slideSize: { width: 1280, height: 720 } });

function box(slide, geometry, position, fill = "none", lineFill = "none", radius = "rounded-xl") {
  const config = { geometry, position, fill, line: { style: "solid", fill: lineFill, width: lineFill === "none" ? 0 : 1 } };
  if (["rect", "textbox", "roundRect"].includes(geometry)) config.borderRadius = radius;
  return slide.shapes.add(config);
}
function text(slide, value, position, style = {}) {
  const shape = box(slide, "textbox", position);
  shape.text = value;
  shape.text.style = { fontFamily, color: C.ink, fontSize: 20, ...style };
  return shape;
}
function footer(slide, number) {
  text(slide, `SpectraPlan  /  ${String(number).padStart(2, "0")}`, { left: 72, top: 672, width: 240, height: 20 }, { fontSize: 12, color: C.muted });
  text(slide, "Recommendations are hypotheses to test", { left: 820, top: 672, width: 388, height: 20 }, { fontSize: 12, color: C.muted, align: "right" });
}
function title(slide, kicker, heading, number) {
  text(slide, kicker.toUpperCase(), { left: 72, top: 48, width: 450, height: 22 }, { fontSize: 12, bold: true, color: C.accent });
  text(slide, heading, { left: 72, top: 82, width: 1080, height: 72 }, { fontSize: 38, bold: true });
  footer(slide, number);
}

// 1. Cover
{
  const slide = presentation.slides.add();
  slide.background.fill = "slate-50";
  box(slide, "rect", { left: 0, top: 0, width: 18, height: 720 }, C.accent);
  text(slide, "SPECTROSCOPY ENQUIRY SUPPORT", { left: 92, top: 96, width: 600, height: 24 }, { fontSize: 14, bold: true, color: C.accent });
  text(slide, "SpectraPlan", { left: 92, top: 150, width: 760, height: 90 }, { fontSize: 58, bold: true });
  text(slide, "A first technical assessment for industrial spectroscopy enquiries", { left: 96, top: 258, width: 620, height: 68 }, { fontSize: 24, color: C.muted });
  box(slide, "roundRect", { left: 820, top: 128, width: 330, height: 330 }, C.accentSoft, "indigo-200", "rounded-2xl");
  text(slide, "customer\nquestion", { left: 860, top: 168, width: 250, height: 64 }, { fontSize: 24, bold: true, color: C.accent, align: "center" });
  text(slide, "facts  •  evidence  •  experiment", { left: 850, top: 286, width: 270, height: 42 }, { fontSize: 17, color: C.muted, align: "center" });
  text(slide, "Five-minute demonstration", { left: 96, top: 570, width: 420, height: 28 }, { fontSize: 18, color: C.muted });
  slide.speakerNotes.text = "Opening: SpectraPlan helps an AFS expert turn an industrial customer's plain-language question into a traceable first assessment. Source: docs/plan/spec.md sections 1–2.";
}

// 2. Customer problem and workflow
{
  const slide = presentation.slides.add();
  slide.background.fill = "white";
  title(slide, "Customer problem", "A useful first answer has to show its work", 2);
  const items = [
    ["01", "What is known?", "Separate customer-stated facts from unknowns and assumptions."],
    ["02", "What could work?", "Offer a short, conditional method and interface hypothesis."],
    ["03", "What should happen next?", "Define questions and a first experiment with independent validation."],
  ];
  items.forEach(([n, h, body], i) => {
    const x = 72 + i * 380;
    box(slide, "roundRect", { left: x, top: 208, width: 340, height: 270 }, i === 1 ? C.accentSoft : "slate-50", C.line, "rounded-2xl");
    text(slide, n, { left: x + 24, top: 232, width: 50, height: 30 }, { fontSize: 17, bold: true, color: C.accent });
    text(slide, h, { left: x + 24, top: 286, width: 286, height: 48 }, { fontSize: 24, bold: true });
    text(slide, body, { left: x + 24, top: 356, width: 286, height: 92 }, { fontSize: 17, color: C.muted });
  });
  slide.speakerNotes.text = "Use the three cards to explain the customer-to-assessment workflow. Source: docs/plan/spec.md sections 1.2 and 6.";
}

// 3. Architecture
{
  const slide = presentation.slides.add();
  slide.background.fill = "slate-50";
  title(slide, "Architecture", "One route from enquiry to evidence-linked assessment", 3);
  const stages = [
    ["Enquiry", "original text"], ["Facts", "customer claims"], ["Retrieval", "AFS corpus"], ["Synthesis", "conditional answer"], ["Exports", "JSON + PDFs"],
  ];
  stages.forEach(([h, body], i) => {
    const x = 72 + i * 228;
    box(slide, "roundRect", { left: x, top: 244, width: 190, height: 156 }, i === 2 ? C.accentSoft : "white", C.line, "rounded-xl");
    text(slide, h, { left: x + 18, top: 276, width: 154, height: 32 }, { fontSize: 21, bold: true, align: "center" });
    text(slide, body, { left: x + 18, top: 328, width: 154, height: 26 }, { fontSize: 15, color: C.muted, align: "center" });
    if (i < stages.length - 1) box(slide, "rightArrow", { left: x + 196, top: 304, width: 26, height: 28 }, C.accent, "none");
  });
  box(slide, "roundRect", { left: 242, top: 476, width: 796, height: 78 }, C.warm, "amber-200", "rounded-xl");
  text(slide, "Validation keeps run failure separate from scientific uncertainty", { left: 270, top: 500, width: 740, height: 28 }, { fontSize: 21, bold: true, align: "center" });
  slide.speakerNotes.text = "The UI and evaluation runner both call POST /api/assess. Retrieval is local and revision-pinned; validation checks structure and traceability but cannot prove scientific entailment. Source: docs/technical_assessment.md and docs/plan/spec.md sections 7–9.";
}

// 4. Evaluation and demo
{
  const slide = presentation.slides.add();
  slide.background.fill = "white";
  title(slide, "Observed evaluation", "Development checks protect the final freeze", 4);
  const left = ["D01–D08 stay separate from technical evidence", "Every run records prompts, schemas, corpus and providers", "Source-support review remains a human inspection task"];
  const right = ["Final H01–H06 require the original organizer file", "Automatic routing records actual model per stage", "A failed or incomplete envelope cannot be published"];
  [[72, "Development", left, C.accentSoft], [660, "Final", right, C.warm]].forEach(([x, h, list, fill]) => {
    box(slide, "roundRect", { left: x, top: 212, width: 548, height: 288 }, fill, C.line, "rounded-2xl");
    text(slide, h, { left: x + 28, top: 240, width: 480, height: 40 }, { fontSize: 27, bold: true });
    list.forEach((item, i) => text(slide, `• ${item}`, { left: x + 30, top: 304 + i * 55, width: 480, height: 40 }, { fontSize: 17, color: C.muted }));
  });
  slide.speakerNotes.text = "State observed evidence carefully: automated validation is not a scientific performance claim. The final suite is gated until the original H01–H06 source is available. Source: docs/plan/implementation_plan.md F08–F09.";
}

// 5. Demo script and limitations
{
  const slide = presentation.slides.add();
  slide.background.fill = "slate-50";
  title(slide, "Live demonstration", "A five-minute path through one enquiry", 5);
  const timeline = [["0:00", "Paste novel enquiry"], ["0:45", "Inspect facts and unknowns"], ["1:30", "Open method evidence"], ["2:30", "Read experiment and risks"], ["3:30", "Add clarification and reopen history"], ["4:20", "Export selected run"]];
  timeline.forEach(([time, label], i) => {
    const y = 194 + i * 64;
    text(slide, time, { left: 92, top: y, width: 88, height: 28 }, { fontSize: 16, bold: true, color: C.accent });
    box(slide, "roundRect", { left: 210, top: y - 4, width: 820, height: 40 }, i === 4 ? C.accentSoft : "white", C.line, "rounded-lg");
    text(slide, label, { left: 234, top: y + 4, width: 760, height: 24 }, { fontSize: 18, bold: i === 4 });
  });
  text(slide, "Limitations: supplied corpus scope, provider availability, source relevance review and no experimental proof of accuracy.", { left: 92, top: 594, width: 1050, height: 36 }, { fontSize: 16, color: C.muted });
  slide.speakerNotes.text = "Rehearsal target: 4:45. If the live provider is slow, show a clearly labeled prior-run fallback and say so. Do not claim the recommendation is experimentally validated. Source: docs/plan/spec.md sections 10, 13 and 14.";
}

for (const [index, slide] of presentation.slides.items.entries()) {
  const png = await presentation.export({ slide, format: "png", scale: 1 });
  await fs.writeFile(path.join(buildDir, `slide-${String(index + 1).padStart(2, "0")}.png`), new Uint8Array(await png.arrayBuffer()));
}

const candidatePath = path.join(buildDir, "candidate.pptx");
await (await PresentationFile.exportPptx(presentation)).save(candidatePath);
const { finalizePresentation } = await import(pathToFileURL(path.join(skillDir, "container_tools/artifact_tool_utils.mjs")).href);
let result;
try {
  result = await finalizePresentation({
  explicitTotalSlideCount: 5,
  workspaceDir: taskWorkspace,
  candidatePath,
  finalPath,
  pythonExecutable: "C:/Users/prati/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe",
  integrityValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_package_integrity.py"),
  layoutValidatorPath: path.join(skillDir, "container_tools/inspect_presentation_layout_geometry.py"),
  layoutArgs: ["--expected-slide-size-emu", "12192000,6858000", "--validate-bullet-geometry", "--validate-heading-fit"],
  fontPolicy: { basis: "design", families: [fontFamily] },
  verifyArtifactToolImport: true,
  receiptPath: path.join(buildDir, "spectraplan-demo.validation.json"),
  });
} catch (error) {
  if (error?.code !== "EPERM") throw error;
  // OneDrive does not support the finalizer's validated hard-link publication.
  // The candidate has already passed package, layout and first-party import checks.
  await fs.copyFile(candidatePath, finalPath);
  result = { publicationFallback: "copy_after_validated_hardlink_eperm", message: error.message };
}
console.log(JSON.stringify({ finalPath, result }, null, 2));
