import { useEffect, useState } from "react";
import {
  getAiModels,
  getAiSettings,
  getRecurringSettings,
  getUploadLogs,
  updateAiSettings,
  updateRecurringSettings,
} from "../api/client";
import { Button, Card, Field, PageHeader, TableContainer } from "../components/ui";

interface ModelInfo {
  id: string;
  label: string;
  input_per_1m: number;
  output_per_1m: number;
  est_cost_per_1000_txns: number;
}

interface ModelsCatalog {
  providers: Record<string, ModelInfo[]>;
  token_estimate_assumptions: {
    input_tokens_per_txn: number;
    output_tokens_per_txn: number;
    note: string;
  };
}

interface AiSettings {
  ai_provider: string;
  openai_model: string;
  anthropic_model: string;
  openrouter_model: string;
  openai_key_configured: boolean;
  anthropic_key_configured: boolean;
  openrouter_key_configured: boolean;
}

interface UploadLog {
  id: number;
  filename: string;
  bank: string | null;
  format_detected: string | null;
  uploaded_at: string;
  rows_parsed: number;
  rows_imported: number;
  rows_skipped: number;
  rows_failed: number;
  status: string;
  error: string | null;
}

const PROVIDERS = [
  { id: "openai", label: "OpenAI", envVar: "OPENAI_API_KEY", keyConfigured: (s: AiSettings) => s.openai_key_configured },
  {
    id: "anthropic",
    label: "Claude (Anthropic)",
    envVar: "ANTHROPIC_API_KEY",
    keyConfigured: (s: AiSettings) => s.anthropic_key_configured,
  },
  {
    id: "openrouter",
    label: "OpenRouter (Jev)",
    envVar: "OPENROUTER_API_KEY",
    keyConfigured: (s: AiSettings) => s.openrouter_key_configured,
  },
] as const;

function formatPrice(value: number): string {
  if (value === 0) return "free";
  return `$${value < 0.1 ? value.toFixed(3) : value.toFixed(2)}`;
}

function formatEstimate(value: number): string {
  return value < 0.01 ? "< $0.01" : `$${value.toFixed(2)}`;
}

function KeyStatus({ configured, envVar }: { configured: boolean; envVar: string }) {
  if (configured) {
    return <span className="key-status key-status-ok">API key configured</span>;
  }
  return (
    <span className="key-status key-status-missing">
      Not configured — set {envVar} in your environment
    </span>
  );
}

function SectionHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className="settings-section-header">
      <h3>{title}</h3>
      <p>{description}</p>
    </div>
  );
}

export default function SettingsPage() {
  const [settings, setSettings] = useState<AiSettings | null>(null);
  const [catalog, setCatalog] = useState<ModelsCatalog | null>(null);
  const [provider, setProvider] = useState("openai");
  const [openaiModel, setOpenaiModel] = useState("");
  const [anthropicModel, setAnthropicModel] = useState("");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [logs, setLogs] = useState<UploadLog[]>([]);
  const [recurringThreshold, setRecurringThreshold] = useState("");
  const [recurringSaving, setRecurringSaving] = useState(false);
  const [recurringSaved, setRecurringSaved] = useState(false);
  const [recurringError, setRecurringError] = useState<string | null>(null);

  const loadData = async () => {
    const [s, m] = await Promise.all([getAiSettings(), getAiModels()]);
    setSettings(s);
    setCatalog(m);
    setProvider(s.ai_provider);
    setOpenaiModel(s.openai_model);
    setAnthropicModel(s.anthropic_model);
  };

  const loadLogs = async () => {
    const res = await getUploadLogs();
    setLogs(res.logs || []);
  };

  const loadRecurring = async () => {
    const res = await getRecurringSettings();
    setRecurringThreshold(res.recurring_large_threshold);
  };

  // Loaded independently of loadData() so a slow/failed logs fetch never
  // blocks the AI settings card (guarded by `!settings || !catalog` below).
  useEffect(() => {
    loadData();
    loadLogs();
    loadRecurring();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSaved(false);
    await updateAiSettings({
      ai_provider: provider,
      openai_model: openaiModel,
      anthropic_model: anthropicModel,
    });
    await loadData();
    setSaving(false);
    setSaved(true);
  };

  const handleSaveRecurring = async () => {
    setRecurringSaving(true);
    setRecurringSaved(false);
    setRecurringError(null);
    const res = await updateRecurringSettings(recurringThreshold);
    if (res.detail) {
      setRecurringError(res.detail);
    } else {
      setRecurringThreshold(res.recurring_large_threshold);
      setRecurringSaved(true);
    }
    setRecurringSaving(false);
  };

  if (!settings || !catalog) return <Card>Loading...</Card>;

  const providerInfo = PROVIDERS.find((p) => p.id === provider) ?? PROVIDERS[0];
  const isJev = provider === "openrouter";
  const currentModels = catalog.providers[provider] ?? [];
  const currentModelId =
    provider === "anthropic" ? anthropicModel : provider === "openai" ? openaiModel : settings.openrouter_model;
  const currentModelInfo = currentModels.find((m) => m.id === currentModelId) ?? currentModels[0];

  const pricingLine = currentModelInfo
    ? `${formatPrice(currentModelInfo.input_per_1m)} in / ${formatPrice(currentModelInfo.output_per_1m)} out per 1M tokens · est. ${formatEstimate(currentModelInfo.est_cost_per_1000_txns)} per 1,000 transactions`
    : null;

  return (
    <div className="settings-page">
      <PageHeader title="Settings" />

      <Card>
        <SectionHeader
          title="AI categorization"
          description="Which provider categorizes imported transactions and the uncategorized backlog."
        />

        <Field label="AI provider" htmlFor="provider-select">
          <select
            id="provider-select"
            className="form-control"
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
          >
            {PROVIDERS.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </Field>

        <Field label="API key">
          <KeyStatus configured={providerInfo.keyConfigured(settings)} envVar={providerInfo.envVar} />
        </Field>

        <Field
          label="Model"
          htmlFor="model-select"
          hint={
            <>
              {isJev && (
                <span className="form-hint-line">
                  Jev classifies each transaction on its own, line by line. Lines it isn't confident about
                  stay Uncategorized so you can review them.
                </span>
              )}
              {pricingLine && <span className="form-hint-line">{pricingLine}</span>}
            </>
          }
        >
          {isJev ? (
            <input
              id="model-select"
              className="form-control"
              readOnly
              value={currentModelInfo?.label ?? settings.openrouter_model}
            />
          ) : (
            <select
              id="model-select"
              className="form-control"
              value={currentModelId}
              onChange={(e) =>
                provider === "anthropic" ? setAnthropicModel(e.target.value) : setOpenaiModel(e.target.value)
              }
            >
              {currentModels.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          )}
        </Field>

        <div className="settings-actions">
          <Button onClick={handleSave} disabled={saving}>
            {saving ? "Saving..." : "Save"}
          </Button>
          {saved && !saving && <span className="settings-saved">Saved.</span>}
        </div>
      </Card>

      <Card>
        <SectionHeader
          title="Recurring expenses"
          description="When a repeating merchant counts as a large recurring expense."
        />

        <Field
          label="Recurring large-expense threshold (base currency)"
          htmlFor="recurring-threshold-input"
          hint="A merchant that recurs across 3+ months at or above this amount shows up as a recurring large expense on the Analysis page, with a warning if the amount changes."
        >
          <input
            id="recurring-threshold-input"
            className="form-control"
            type="number"
            min="0.01"
            step="0.01"
            value={recurringThreshold}
            onChange={(e) => setRecurringThreshold(e.target.value)}
          />
        </Field>

        <div className="settings-actions">
          <Button onClick={handleSaveRecurring} disabled={recurringSaving}>
            {recurringSaving ? "Saving..." : "Save"}
          </Button>
          {recurringSaved && !recurringSaving && <span className="settings-saved">Saved.</span>}
          {recurringError && <span className="key-status key-status-missing">{recurringError}</span>}
        </div>
      </Card>

      <Card>
        <SectionHeader title="Upload history" description="Recent CSV imports and their outcome." />
        <TableContainer className="settings-upload-table">
          <table>
            <thead>
              <tr>
                <th>Uploaded</th>
                <th>File</th>
                <th>Bank/Format</th>
                <th>Parsed</th>
                <th>Imported</th>
                <th>Skipped</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {logs.map((log) => (
                <tr key={log.id}>
                  <td>{new Date(log.uploaded_at).toLocaleString("en-GB")}</td>
                  <td>{log.filename}</td>
                  <td>{log.bank || log.format_detected || "-"}</td>
                  <td>{log.rows_parsed}</td>
                  <td>{log.rows_imported}</td>
                  <td>{log.rows_skipped}</td>
                  <td>
                    {log.status === "success" ? (
                      "Success"
                    ) : (
                      <span title={log.error ?? undefined}>
                        Failed{log.error ? `: ${log.error}` : ""}
                      </span>
                    )}
                  </td>
                </tr>
              ))}
              {logs.length === 0 && (
                <tr>
                  <td colSpan={7} className="empty-state">
                    No uploads yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </TableContainer>
      </Card>
    </div>
  );
}
