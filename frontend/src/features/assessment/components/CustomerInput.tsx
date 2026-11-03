export default function CustomerInput({ draft, change }: { draft: string; change: (text: string) => void }) {
  return <section className="enquiry-editor" aria-labelledby="enquiry-heading">
    <h1 id="enquiry-heading"><label htmlFor="enquiry">Customer enquiry</label></h1>
    <textarea id="enquiry" value={draft} onChange={event => change(event.target.value)} placeholder="Describe the process and what you want to measure…" rows={4} />
  </section>
}
