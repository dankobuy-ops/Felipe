import { useState } from "react";
import type { BusinessInsurance } from "@/data/businessInsurances";

function ContentLines({ text }: { text: string }) {
  const lines = text.split("\n").filter(Boolean);
  return (
    <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "10px" }}>
      {lines.map((line, i) => {
        const colonIdx = line.indexOf(": ");
        if (colonIdx > 0 && colonIdx < 45) {
          const label = line.slice(0, colonIdx);
          const rest = line.slice(colonIdx + 2);
          return (
            <li key={i} style={{ display: "flex", gap: "8px", alignItems: "flex-start", fontSize: "15px", color: "#2c2c2c", lineHeight: "1.7" }}>
              <span style={{ color: "#C7A965", fontWeight: 700, flexShrink: 0, marginTop: "1px" }}>•</span>
              <span><strong style={{ color: "#1b1b1b" }}>{label}:</strong> {rest}</span>
            </li>
          );
        }
        return (
          <li key={i} style={{ display: "flex", gap: "8px", alignItems: "flex-start", fontSize: "15px", color: "#2c2c2c", lineHeight: "1.7" }}>
            <span style={{ color: "#C7A965", fontWeight: 700, flexShrink: 0, marginTop: "1px" }}>•</span>
            <span>{line}</span>
          </li>
        );
      })}
    </ul>
  );
}

function InsuranceItem({ ins }: { ins: BusinessInsurance }) {
  const [isOpen, setIsOpen] = useState(false);
  const activeTabs = ins.tabs.filter((t) => t.content.trim());
  const [activeTab, setActiveTab] = useState(activeTabs[0]?.label ?? "");

  return (
    <div style={{ borderBottom: "1px solid #e2e4e8" }}>
      {/* Outer header */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        style={{
          width: "100%",
          display: "flex",
          alignItems: "center",
          gap: "16px",
          padding: "20px 0",
          background: "transparent",
          border: "none",
          cursor: "pointer",
          textAlign: "left",
        }}
      >
        <span
          style={{
            fontFamily: "'Cinzel', serif",
            fontSize: "22px",
            fontWeight: 400,
            color: "#C7A965",
            lineHeight: 1,
            width: "20px",
            flexShrink: 0,
          }}
        >
          {isOpen ? "—" : "+"}
        </span>
        <span
          style={{
            fontFamily: "'Cinzel', serif",
            fontSize: "15px",
            fontWeight: 600,
            color: "#C7A965",
            letterSpacing: "0.04em",
            textTransform: "uppercase",
          }}
        >
          {ins.title}
        </span>
      </button>

      {/* Expanded content */}
      {isOpen && (
        <div style={{ paddingBottom: "28px", paddingLeft: "36px" }}>
          {/* Summary */}
          {ins.summary && (
            <p style={{ fontSize: "15px", color: "#55556d", lineHeight: "1.75", marginBottom: "24px" }}>
              {ins.summary}
            </p>
          )}

          {activeTabs.length === 0 ? (
            <p style={{ fontSize: "14px", color: "#8D99AE", fontStyle: "italic" }}>
              Información disponible próximamente.
            </p>
          ) : (
            <>
              {/* Tab buttons */}
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: "8px",
                  marginBottom: "24px",
                }}
              >
                {activeTabs.map((tab) => {
                  const isActive = activeTab === tab.label;
                  return (
                    <button
                      key={tab.label}
                      onClick={() => setActiveTab(tab.label)}
                      style={{
                        fontFamily: "'Cinzel', serif",
                        fontSize: "11px",
                        fontWeight: 600,
                        letterSpacing: "0.06em",
                        textTransform: "uppercase",
                        padding: "8px 16px",
                        borderRadius: "4px",
                        border: `1px solid ${isActive ? "#C7A965" : "#c8cacd"}`,
                        background: isActive ? "#C7A965" : "transparent",
                        color: isActive ? "#261c30" : "#8D99AE",
                        cursor: "pointer",
                        transition: "all 0.15s ease",
                      }}
                    >
                      {tab.label}
                    </button>
                  );
                })}
              </div>

              {/* Active tab content */}
              {activeTabs
                .filter((t) => t.label === activeTab)
                .map((tab) => (
                  <ContentLines key={tab.label} text={tab.content} />
                ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export function InsuranceAccordion({ insurances }: { insurances: BusinessInsurance[] }) {
  return (
    <div style={{ borderTop: "1px solid #e2e4e8" }}>
      {insurances.map((ins) => (
        <InsuranceItem key={ins.slug} ins={ins} />
      ))}
    </div>
  );
}
