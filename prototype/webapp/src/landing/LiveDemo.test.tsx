import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LiveDemo } from "./LiveDemo";

// The landing's demo (SCRIPTED): the real card component, answered in the browser, nothing sent.
describe("LiveDemo", () => {
  it("says it is a scripted example", () => {
    render(<LiveDemo />);
    expect(screen.getByText(/no AI runs here and nothing is saved/i)).toBeInTheDocument();
  });

  it("confirming the ownership card credits the visitor and adds the task for Sara", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    render(<LiveDemo />);
    await userEvent.click(screen.getByRole("button", { name: /confirm/i }));
    expect(screen.getByText("Confirmed by You")).toBeInTheDocument();
    expect(screen.getByText(/Added to Tasks: Write the user test plan · Sara · 27 Nov/)).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();
    fetchSpy.mockRestore();
  });

  it("choosing an option closes the decision", async () => {
    render(<LiveDemo />);
    await userEvent.click(screen.getByRole("tab", { name: "Decision" }));
    expect(screen.getByRole("tab", { name: "Decision" })).toHaveAttribute("aria-selected", "true");
    await userEvent.click(screen.getByRole("button", { name: "SUS" }));
    expect(screen.getByText(/Added to Decisions: SUS/)).toBeInTheDocument();
  });

  it("arrow keys move between situations", async () => {
    render(<LiveDemo />);
    screen.getByRole("tab", { name: "Ownership" }).focus();
    await userEvent.keyboard("{ArrowRight}");
    expect(screen.getByRole("tab", { name: "Dependency" })).toHaveFocus();
    expect(screen.getByText("Finish the API endpoints")).toBeInTheDocument();
  });
});
