/**
 * The answer-first pattern (P2.2): the page's core question, answered in plain
 * text before anything else.
 *
 * Pure server-rendered HTML — no client component, no JS required to read it —
 * because the readers this exists for include crawlers and answer engines that
 * execute nothing. The visual treatment marks it as the page's summary; the
 * markup keeps it an ordinary heading + paragraph, which is what gets quoted.
 *
 * Discipline, not decoration: the answer must stand alone in ≤ 50 words,
 * factual and conditional where the facts are conditional. A DirectAnswer that
 * needs the rest of the page to be true is just an intro with a border.
 */
export function DirectAnswer({
  question,
  children,
}: {
  question: string;
  children: React.ReactNode;
}) {
  return (
    <section className="direct-answer" aria-label="Réponse directe">
      <h2 className="direct-answer__question">{question}</h2>
      <div className="direct-answer__text">{children}</div>
    </section>
  );
}
