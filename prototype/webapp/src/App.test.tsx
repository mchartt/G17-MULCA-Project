// Which page the app shows for each address: landing, /login, invite links.
import { render, screen } from "@testing-library/react";
import { App } from "./App";

beforeEach(() => {
  localStorage.clear();
  // No adapter in these tests: every request fails, as on the online preview.
  vi.stubGlobal("fetch", async () => new Response("{}", { status: 503 }));
  vi.stubGlobal("IntersectionObserver", class { observe() {} disconnect() {} });
  vi.stubGlobal("scrollTo", () => {});
  // Reduced motion: no smooth scrolling and no film playback in jsdom.
  vi.stubGlobal("matchMedia", (q: string) => ({ matches: q.includes("reduce"), addEventListener() {}, removeEventListener() {} }));
});

afterEach(() => history.replaceState(null, "", "/"));

test("the landing links to the login page instead of holding the forms", () => {
  history.replaceState(null, "", "/");
  render(<App />);
  expect(screen.getByRole("link", { name: /Log in or create an account/ })).toHaveAttribute("href", "/login");
  expect(screen.getByRole("link", { name: "Open your space" })).toHaveAttribute("href", "/login");
  expect(screen.queryByRole("tab", { name: "Log in" })).not.toBeInTheDocument();
});

test("/login shows the forms and the privacy notice", async () => {
  history.replaceState(null, "", "/login");
  render(<App />);
  expect(screen.getByRole("heading", { level: 1, name: "Open your group's space." })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "What Cadence reads and keeps" })).toBeInTheDocument();
  expect(await screen.findByRole("tab", { name: "Log in" })).toBeInTheDocument();
});

test("an old invite link (/?code=...) opens the login page and keeps the code", () => {
  history.replaceState(null, "", "/?code=ABCDEFGH23");
  render(<App />);
  expect(location.pathname).toBe("/login");
  expect(location.search).toBe("?code=ABCDEFGH23");
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Join your group's space.");
});
