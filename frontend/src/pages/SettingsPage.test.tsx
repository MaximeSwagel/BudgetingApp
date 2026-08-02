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
};

const MODELS_CATALOG = {
  providers: {
    openai: [
      { id: "gpt-4o-mini", label: "GPT-4o mini", input_per_1m: 0.15, output_per_1m: 0.6, est_cost_per_1000_txns: 0.01 },
    ],
    anthropic: [
      { id: "claude-haiku-4-5", label: "Claude Haiku 4.5", input_per_1m: 1, output_per_1m: 5, est_cost_per_1000_txns: 0.05 },
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
});
