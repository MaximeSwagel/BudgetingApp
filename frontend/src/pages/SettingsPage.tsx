import { useEffect, useState } from "react";
import { getAiModels, getAiSettings, getUploadLogs, updateAiSettings } from "../api/client";
import { Button, Card, PageHeader, TableContainer } from "../components/ui";

interface ModelInfo {
  id: string;
  label: string;
  input_per_1m: number;
  output_per_1m: number;
  est_cost_per_1000_txns: number;
}

interface ModelsCatalog {
  providers: { openai: ModelInfo[]; anthropic: ModelInfo[] };
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
  openai_key_configured: boolean;
  anthropic_key_configured: boolean;
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

const PROVIDER_LABELS: Record<string, string> = {
  openai: "OpenAI",
  anthropic: "Claude (Anthropic)",
};

function KeyStatus({ configured, providerLabel }: { configured: boolean; providerLabel: string }) {
  if (configured) {
    return <span className="key-status key-status-ok">API key configured</span>;
  }
  const envVar = providerLabel === "OpenAI" ? "OPENAI_API_KEY" : "ANTHROPIC_API_KEY";
  return (
    <span className="key-status key-status-missing">
      Not configured — set {envVar} in your environment
    </span>
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

  // Loaded independently of loadData() so a slow/failed logs fetch never
  // blocks the AI settings card (guarded by `!settings || !catalog` below).
  useEffect(() => {
    loadData();
    loadLogs();
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

  if (!settings || !catalog) return <Card>Loading...</Card>;

  const currentModelId = provider === "anthropic" ? anthropicModel : openaiModel;
  const currentModels = catalog.providers[provider as "openai" | "anthropic"];
  const currentModelInfo = currentModels.find((m) => m.id === currentModelId);

  return (
    <div>
      <PageHeader title="Settings" actions={<span className="dash-period">AI Categorization</span>} />

      <div className="settings-content">
        <Card className="settings-grid">
          <div className="settings-field">
            <label className="settings-label" htmlFor="provider-select">
              AI Provider
            </label>
            <select
              id="provider-select"
              value={provider}
              onChange={(e) => setProvider(e.target.value)}
            >
              <option value="openai">OpenAI</option>
              <option value="anthropic">Claude (Anthropic)</option>
            </select>
          </div>

          <div className="settings-field">
            <span className="settings-label">API key status</span>
            <div className="key-status-row">
              <KeyStatus configured={settings.openai_key_configured} providerLabel="OpenAI" />
              <KeyStatus configured={settings.anthropic_key_configured} providerLabel="Claude (Anthropic)" />
            </div>
          </div>

          <div className="settings-field">
            <label className="settings-label" htmlFor="model-select">
              Model ({PROVIDER_LABELS[provider]})
            </label>
            <select
              id="model-select"
              value={currentModelId}
              onChange={(e) =>
                provider === "anthropic"
                  ? setAnthropicModel(e.target.value)
                  : setOpenaiModel(e.target.value)
              }
            >
              {currentModels.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label} — ${m.input_per_1m.toFixed(2)}/$
                  {m.output_per_1m.toFixed(2)} per 1M tokens (in/out)
                </option>
              ))}
            </select>
            {currentModelInfo && (
              <div className="settings-model-option">
                Estimated cost: ${currentModelInfo.est_cost_per_1000_txns.toFixed(2)} per 1,000 categorized
                transactions.
              </div>
            )}
          </div>

          <div className="settings-field">
            <Button onClick={handleSave} disabled={saving}>
              {saving ? "Saving..." : "Save"}
            </Button>
            {saved && !saving && <span className="settings-saved">Saved.</span>}
          </div>
        </Card>

        <Card>
          <h3>Upload History</h3>
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
    </div>
  );
}
