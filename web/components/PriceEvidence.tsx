import {
  basisLabel,
  formatAmount,
  formatPrice,
  qualificationLabel,
  systemSizeLabel,
  vatIsUnknown,
  vatLabel,
} from "@/lib/format";
import type { ListItem, ObservedRange, PriceAnswer } from "@/lib/types";

/**
 * Evidence-backed price display.
 *
 * Each figure is shown with the context its source actually stated: basis, VAT
 * treatment, system size, what is included. Unknowns are shown as unknown. That
 * is not a hedge — a €6 000 figure with no basis could be a total, a per-kWc rate
 * or a per-m² price, and presenting it bare would be the misleading option.
 *
 * Nothing here renders a source URL or a claim identifier. The DTO does not carry
 * them, and Phase 3.3 shipped a competitor link the one time content was allowed
 * to carry its own references.
 */

export function PriceCard({ answer }: { answer: PriceAnswer }) {
  const size = systemSizeLabel(answer.system_size_kwp ?? []);
  const vatUnknown = vatIsUnknown(answer.vat_status);
  return (
    <li className="price-card">
      <div className="price-card__amount">{formatPrice(answer)}</div>
      <div className="price-card__basis">{basisLabel(answer.basis)}</div>
      <div className="price-card__meta">
        <span className={`tag${vatUnknown ? " tag--unknown" : ""}`}>
          {vatLabel(answer.vat_status)}
        </span>
        {size ? <span className="tag">{size}</span> : null}
        {answer.installation_included === true ? (
          <span className="tag">pose comprise</span>
        ) : null}
        {answer.installation_included === false ? (
          <span className="tag">pose non comprise</span>
        ) : null}
        {answer.battery_included === true ? (
          <span className="tag">batterie comprise</span>
        ) : null}
        {answer.battery_included === false ? (
          <span className="tag">batterie non comprise</span>
        ) : null}
        <span className="tag">{qualificationLabel(answer.category)}</span>
      </div>
    </li>
  );
}

/** A price list that came out of the content body rather than the evidence block. */
export function PriceList({ items }: { items: ListItem[] }) {
  return (
    <ul className="price-list">
      {items.map((item, index) => (
        <li className="price-card" key={index}>
          <div className="price-card__amount">{item.text}</div>
        </li>
      ))}
    </ul>
  );
}

export function PriceEvidenceBlock({
  answers,
  observedRange,
}: {
  answers: PriceAnswer[];
  observedRange?: ObservedRange | null;
}) {
  if (!answers || answers.length === 0) return null;
  const anyVatUnknown = answers.some((a) => vatIsUnknown(a.vat_status));
  return (
    <section className="section" aria-labelledby="prix-observes">
      <h2 id="prix-observes">Prix relevés dans les sources</h2>
      <ul className="price-list">
        {answers.map((answer, index) => (
          <PriceCard answer={answer} key={index} />
        ))}
      </ul>

      {observedRange ? (
        <p className="evidence-note">
          Fourchette observée sur {observedRange.observation_count} relevés
          comparables&nbsp;: {formatAmount(observedRange.low, observedRange.currency)} –{" "}
          {formatAmount(observedRange.high, observedRange.currency)}{" "}
          {basisLabel(observedRange.basis)}, {vatLabel(observedRange.vat_status)}. Il
          s&apos;agit d&apos;un échantillon observé, et non d&apos;une moyenne du
          marché belge.
        </p>
      ) : null}

      <p className="evidence-note">
        Ces montants sont ceux annoncés par les sources consultées, à la date de la
        recherche. Ils ne constituent pas une moyenne nationale ni un devis.
        {anyVatUnknown
          ? " Lorsque la source ne précise pas le traitement de la TVA, nous l'indiquons plutôt que de le supposer."
          : ""}
      </p>
    </section>
  );
}
