import type { ListItem, Section, TextRun } from "@/lib/types";
import { PriceList } from "./PriceEvidence";

/**
 * Renders sanitized content sections.
 *
 * There is no `dangerouslySetInnerHTML` anywhere in this file, and there is no
 * code path that could produce one: the input is typed nodes carrying plain text,
 * and React escapes text. That is the whole XSS story for generated content.
 */

function Runs({ runs }: { runs: TextRun[] }) {
  return (
    <>
      {runs.map((run, index) => {
        if (run.mark === "strong") return <strong key={index}>{run.text}</strong>;
        if (run.mark === "em") return <em key={index}>{run.text}</em>;
        if (run.mark === "code") return <code key={index}>{run.text}</code>;
        return <span key={index}>{run.text}</span>;
      })}
    </>
  );
}

function Bullets({ items }: { items: ListItem[] }) {
  return (
    <ul>
      {items.map((item, index) => (
        <li key={index}>
          <Runs runs={item.runs} />
        </li>
      ))}
    </ul>
  );
}

/**
 * The H1 is rendered by the page, not by this component: a content body that
 * happened to contain two `#` headings would otherwise produce two H1s and a
 * blocking SEO QA finding on a page that already passed QA.
 */
export function Prose({ sections, skipFirstH1 = true }: {
  sections: Section[];
  skipFirstH1?: boolean;
}) {
  let h1Skipped = !skipFirstH1;
  return (
    <div className="prose">
      {sections.map((section, index) => {
        if (section.type === "heading") {
          if (section.level === 1) {
            if (!h1Skipped) {
              h1Skipped = true;
              return null;
            }
            return <h2 key={index}>{section.text}</h2>;
          }
          const Tag = (section.level === 2 ? "h2" : "h3") as "h2" | "h3";
          return <Tag key={index}>{section.text}</Tag>;
        }
        if (section.type === "paragraph") {
          return (
            <p key={index}>
              <Runs runs={section.runs} />
            </p>
          );
        }
        if (section.type === "price_list") {
          return <PriceList key={index} items={section.items} />;
        }
        return <Bullets key={index} items={section.items} />;
      })}
    </div>
  );
}
