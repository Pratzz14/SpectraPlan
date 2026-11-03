"""Offline, paginated PDF export of a stored analysis and its audit trail."""

from html import escape
from io import BytesIO
import re

import pymupdf


def history_pdf(trace):
    def text(value):
        # Allow long identifiers / URLs to wrap without losing their characters.
        return escape(re.sub(r"(\S{55})(?=\S)", lambda m: m[1] + "\u200b", str(value))).replace("\n", "<br>")

    def render(value, depth=0):
        if isinstance(value, dict):
            return "".join(f"<p><b>{text(key.replace('_', ' ').capitalize())}</b></p>" + render(item, depth + 1)
                           for key, item in value.items())
        if isinstance(value, list):
            return "".join(f"<p><b>Item {index + 1}</b></p>" + render(item, depth + 1)
                           for index, item in enumerate(value)) or "<p>None recorded.</p>"
        return f"<p>{text(value) if value is not None else 'Not recorded'}</p>"

    sections = [("Customer enquiry", trace["draft_description"] or trace["description"]),
                ("Clarification answers", trace["clarification_answers"]),
                ("Clarification questions", trace["questions"]),
                ("Analysis result", trace["run"]),
                ("Chronological retrieval and model trace", trace["events"])]
    html = ("<h1>SpectraPlan</h1><h2>Saved enquiry report</h2>"
            f"<p>Run: {text(trace['run_id'])}<br>Round: {trace['round_no']}<br>"
            f"Created: {text(trace['created_at'])}<br>Status: {text(trace['status'])}</p>"
            "<p>Initial technical assessment only. Source evidence does not establish experimental performance. "
            "Incomplete or interrupted runs may contain only partial records.</p>" +
            "".join(f"<h2>{title}</h2>{render(value)}" for title, value in sections))
    return render_pdf(html)


def render_pdf(html):
    story = pymupdf.Story(html=html, user_css="body {font-family:sans-serif;font-size:10pt;line-height:1.4;color:#17343b} h1 {color:#075747} h2 {font-size:15pt;color:#075747;page-break-after:avoid} h3 {font-size:11pt;page-break-after:avoid} p {margin:5pt 0 8pt} li {margin-bottom:5pt} ")
    stream = BytesIO()
    writer = pymupdf.DocumentWriter(stream)
    more = True
    while more:
        device = writer.begin_page(pymupdf.paper_rect("a4"))
        more, _ = story.place(pymupdf.Rect(42, 42, 553, 790))
        story.draw(device)
        writer.end_page()
    writer.close()
    with pymupdf.open(stream=stream.getvalue(), filetype="pdf") as document:
        for index, page in enumerate(document):
            page.insert_text((42, 820), f"SpectraPlan | Page {index + 1} of {len(document)}", fontsize=8)
        return document.tobytes()


def chemist_pdf(trace):
    """A scientific reading report; excludes provider metadata and retrieval logs."""
    run = trace.get('run') or {}
    assessment = run.get('assessment') or {}
    contexts = (run.get('facts') or {}).get('contexts', [])
    sources = assessment.get('source_index', [])

    def clean(value):
        return escape(str(value)).replace('\n', '<br>')

    def label(value):
        return str(value).replace('_', ' ').capitalize()

    def scope(ids):
        return ', '.join(next((c['label'] for c in contexts if c['context_id'] == cid),
                             f'Sample {index + 1}') for index, cid in enumerate(ids)) or 'All samples'

    def claim(value):
        if not value:
            return ''
        citations = [s['citation'] for s in sources if s['evidence_id'] in value.get('evidence_ids', [])]
        return value.get('text', '') + (f" [{'; '.join(citations)}]" if citations else '')

    blocks = ['<h1>SpectraPlan</h1><h2>Initial spectroscopy assessment</h2>',
              f"<p>Analysis date: {clean(trace['created_at'][:10])} · Round {trace['round_no']}</p>"]

    def paragraph(value):
        if value:
            blocks.append(f'<p>{clean(value)}</p>')

    def section(title, rows):
        rows = [row for row in rows if row]
        if rows:
            blocks.append(f'<h2>{clean(title)}</h2><ul>' + ''.join(f'<li>{clean(row)}</li>' for row in rows) + '</ul>')

    blocks.append('<h2>Enquiry</h2>')
    paragraph(trace.get('draft_description') or trace['description'])
    section('Customer clarifications', [f"{a['context']}: {a['question']} Answer: {a['answer']}"
                                      for a in trace.get('clarification_answers', [])])
    blocks.append('<h2>Assessment at a glance</h2>')
    if not assessment:
        paragraph('Assessment incomplete. No scientific conclusion is available. Retry the analysis before making a method decision.')
        section('Information still needed', (run.get('facts') or {}).get('missing_information', []))
    else:
        paragraph(label(assessment['decision_status']))
        paragraph(assessment['case_summary'])
        paragraph(assessment['decision_reason'])
        requirements = assessment.get('requirements', {})
        section('Customer requirements', [f"{scope([r['context_id']] if r.get('context_id') else [])}: {label(r['field'])}: {r['value']} (customer statement: {r['input_quote']})"
                                          for r in requirements.get('stated', [])])
        section('Information still needed', requirements.get('unknowns', []))
        blocks.append('<h2>Methods worth investigating</h2>')
        if not assessment.get('recommendations'):
            paragraph('No supported method shortlist is available yet. Resolve the questions below and follow the proposed investigation.')
        for recommendation in assessment.get('recommendations', []):
            blocks.append(f"<h3>{clean(recommendation['method'])} · {clean(scope(recommendation['context_ids']))}</h3>")
            paragraph(label(recommendation['status']))
            paragraph(claim(recommendation.get('rationale')))
            paragraph(f"Measurement geometry: {recommendation.get('geometry') or 'To be agreed'}. Measurement location: {recommendation.get('measurement_location') or 'To be agreed'}.")
            spectral = recommendation.get('spectral_range') or {}
            paragraph(f"Spectral range ({label(spectral.get('kind', 'undetermined'))}): {spectral.get('interval') or 'Not established'}")
            for key in ['spectral_range', 'raman_excitation', 'raman_shift']:
                value = spectral if key == 'spectral_range' else spectral.get(key)
                paragraph(claim(value))
            section('Assumptions to confirm', recommendation.get('assumptions', []))
            section('Method limitations', [claim(x) for x in recommendation.get('limitations', [])])
        section('Risks and limitations', [f"{scope(r['context_ids'])}: {claim(r)}" for r in assessment.get('risks', [])])
        section('Questions before proceeding', [f"{scope(q['context_ids'])}: {q['question']} Why this matters: {claim(q.get('reason'))}"
                                              for q in sorted(assessment.get('clarification_questions', []), key=lambda q: q['priority'])])
        experiment = assessment.get('experiment') or {}
        blocks.append('<h2>Proposed feasibility study</h2>')
        paragraph(scope(experiment.get('context_ids', [])))
        paragraph(experiment.get('objective'))
        for title, key in [('Samples', 'samples'), ('Measurements and reference assays', 'measurements'),
                           ('Comparisons', 'comparisons'), ('Variation to cover', 'variation')]:
            section(title, experiment.get(key, []))
        section('Validation approach', [experiment.get('validation')] +
                [f"{scope(g['context_ids'])}: {label(g['study_type'])}; independent unit: {label(g['independent_unit'])}"
                 for g in experiment.get('validation_groups', [])])
        section('Proposed settings to confirm', [f"{scope(s['context_ids'])}: {s['name']} = {s['value']} {s.get('unit') or ''} (proposed, not a customer requirement)"
                                               for s in experiment.get('proposed_settings', [])])
        section('Acceptance criteria', [f"{scope([c['context_id']])}: {label(c['metric'])}: {c.get('threshold') or 'Agree with customer'} ({label(c['origin'])})"
                                        for c in experiment.get('acceptance_criteria', [])])
        section('Go / no-go decision', [experiment.get('decision_criteria')])
        section('Next steps', experiment.get('open_items', []))
        evidence = {e['evidence']['evidence_id']: e['evidence'] for e in (run.get('retrieval') or {}).get('evidence', [])}
        blocks.append('<h2>Evidence and references</h2>')
        if not sources:
            paragraph('No supporting source citations were recorded for this assessment.')
        for source in sources:
            paragraph(source['citation'])
            source_evidence = evidence.get(source['evidence_id'], {})
            paragraph(source_evidence.get('text'))
            for note in source_evidence.get('workbook_notes') or []:
                paragraph(f"Source note: {note['text']}")
    paragraph('This is an initial assessment and a proposed study, not an experimentally validated performance claim. Confirm suitability and acceptance criteria through testing.')
    return render_pdf(''.join(blocks))
