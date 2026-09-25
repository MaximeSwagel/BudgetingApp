import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "../api/client";
import SettingsPage from "./SettingsPage";

vi.mock("../api/client");

const AI_SETTINGS = {
  ai_provider: "openai",
  openai_model: "gpt-4o-mini",
  anthropic_model: "claude-haiku-4-5",
  openai_key_configured: true,
  anthropic_key_configured: false,
  openrouter_model: "~typesafe/jev-latest",
  openrouter_key_configured: false,
};

const MODELS_CATALOG = {
  providers: {
    openai: [
      { id: "gpt-4o-mini", label: "GPT-4o mini", input_per_1m: 0.15, output_per_1m: 0.6, est_cost_per_1000_txns: 0.01 },
    ],
    anthropic: [
      { id: "claude-haiku-4-5", label: "Claude Haiku 4.5", input_per_1m: 1, output_per_1m: 5, est_cost_per_1000_txns: 0.05 },
    ],
    openrouter: [
      { id: "~typesafe/jev-latest", label: "Jev (latest)", input_per_1m: 0.042, output_per_1m: 0, est_cost_per_1000_txns: 0.02 },
    ],
  },
  token_estimate_assumptions: { input_tokens_per_txn: 150, output_tokens_per_txn: 30, note: "" },
};

function setupMocks() {
  vi.mocked(api.getAiSettings).mockResolvedValue(AI_SETTINGS);
  vi.mocked(api.getAiModels).mockResolvedValue(MODELS_CATALOG);
  vi.mocked(api.getUploadLogs).mockResolvedValue({ logs: [] });
  vi.mocked(api.getRecurringSettings).mockResolvedValue({ recurring_large_threshold: "100" });
}

describe("SettingsPage", () => {
  beforeEach(() => {
    vi.mocked(api.getAiSettings).mockReset();
    vi.mocked(api.getAiModels).mockReset();
    vi.mocked(api.getUploadLogs).mockReset();
    vi.mocked(api.getRecurringSettings).mockReset();
    vi.mocked(api.updateRecurringSettings).mockReset();
    vi.mocked(api.updateAiSettings).mockReset();
    setupMocks();
  });

  it("loads and displays the saved recurring threshold", async () => {
    render(<SettingsPage />);

    const input = await screen.findByLabelText(/Recurring large-expense threshold/);
    await waitFor(() => expect(input).toHaveValue(100));
  });

  it("saves an updated recurring threshold", async () => {
    vi.mocked(api.updateRecurringSettings).mockResolvedValue({ recurring_large_threshold: "250" });

    render(<SettingsPage />);

    const input = await screen.findByLabelText(/Recurring large-expense threshold/);
    await waitFor(() => expect(input).toHaveValue(100));

    await userEvent.clear(input);
    await userEvent.type(input, "250");

    const saveButtons = screen.getAllByText("Save");
    await userEvent.click(saveButtons[saveButtons.length - 1]);

    await waitFor(() => expect(api.updateRecurringSettings).toHaveBeenCalledWith("250"));
    await waitFor(() => expect(screen.getAllByText("Saved.").length).toBeGreaterThan(0));
  });

  it("shows an error message when the backend rejects the threshold", async () => {
    vi.mocked(api.updateRecurringSettings).mockResolvedValue({
      detail: "recurring_large_threshold must be positive",
    });

    render(<SettingsPage />);

    const input = await screen.findByLabelText(/Recurring large-expense threshold/);
    await waitFor(() => expect(input).toHaveValue(100));

    await userEvent.clear(input);
    await userEvent.type(input, "0");

    const saveButtons = screen.getAllByText("Save");
    await userEvent.click(saveButtons[saveButtons.length - 1]);

    await waitFor(() =>
      expect(screen.getByText("recurring_large_threshold must be positive")).toBeInTheDocument()
    );
  });

  it("shows a single key status for the selected provider", async () => {
    render(<SettingsPage />);

    await screen.findByLabelText("AI provider");
    expect(screen.getAllByText("API key configured")).toHaveLength(1);
    expect(screen.queryByText(/ANTHROPIC_API_KEY/)).not.toBeInTheDocument();
    expect(screen.queryByText(/OPENROUTER_API_KEY/)).not.toBeInTheDocument();
  });

  it("names the Anthropic env var when that provider is selected and unconfigured", async () => {
    render(<SettingsPage />);

    await userEvent.selectOptions(await screen.findByLabelText("AI provider"), "anthropic");

    expect(
      screen.getByText("Not configured — set ANTHROPIC_API_KEY in your environment")
    ).toBeInTheDocument();
    expect(screen.queryByText("API key configured")).not.toBeInTheDocument();
  });

  it("lists exactly the three providers", async () => {
    render(<SettingsPage />);

    const select = await screen.findByLabelText("AI provider");
    const labels = Array.from(select.querySelectorAll("option")).map((o) => o.textContent);
    expect(labels).toEqual(["OpenAI", "Claude (Anthropic)", "OpenRouter (Jev)"]);
  });

  it("shows a read-only Jev model with the line-by-line note for OpenRouter", async () => {
    render(<SettingsPage />);

    await userEvent.selectOptions(await screen.findByLabelText("AI provider"), "openrouter");

    expect(screen.queryByRole("combobox", { name: /Model/ })).not.toBeInTheDocument();
    const model = screen.getByLabelText(/Model/);
    expect(model).toHaveValue("Jev (latest)");
    expect(model).toHaveAttribute("readonly");
    expect(screen.getByText(/line by line/)).toBeInTheDocument();
    expect(screen.getByText(/stay Uncategorized/)).toBeInTheDocument();
    expect(screen.getByText(/OPENROUTER_API_KEY/)).toBeInTheDocument();
    expect(screen.getByText(/\$0\.042 in \/ free out per 1M tokens/)).toBeInTheDocument();
  });

  it("saves the OpenRouter provider", async () => {
    vi.mocked(api.updateAiSettings).mockResolvedValue({});
    render(<SettingsPage />);

    await userEvent.selectOptions(await screen.findByLabelText("AI provider"), "openrouter");
    await userEvent.click(screen.getAllByText("Save")[0]);

    await waitFor(() =>
      expect(api.updateAiSettings).toHaveBeenCalledWith(
        expect.objectContaining({ ai_provider: "openrouter" })
      )
    );
  });
});
