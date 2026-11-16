import { parseSlash } from "./slash";

test("an ordinary message is not a command", () => {
  expect(parseSlash("see you at 5/6 pm")).toBeNull();
  expect(parseSlash("we could use /planning later")).toBeNull();
  expect(parseSlash("/ planning")).toBeNull();
  expect(parseSlash("@coordinator who does the slides?")).toBeNull();
});

test("/planning alone asks for the tasks; with text it carries them one per line", () => {
  expect(parseSlash("/planning")).toEqual({ kind: "planning", tasks: "" });
  expect(parseSlash("  /Planning  ")).toEqual({ kind: "planning", tasks: "" });
  expect(parseSlash("/planning Server API; UI screens ;; Slides")).toEqual({ kind: "planning", tasks: "Server API\nUI screens\nSlides" });
  expect(parseSlash("/planning\nServer API\n\nUI screens")).toEqual({ kind: "planning", tasks: "Server API\nUI screens" });
});

test("/checkin takes no argument", () => {
  expect(parseSlash("/checkin")).toEqual({ kind: "checkin" });
  expect(parseSlash("/checkin now please")).toEqual({ kind: "checkin" });
});

test("any other slash word is named back, never posted", () => {
  expect(parseSlash("/summary")).toEqual({ kind: "unknown", name: "summary" });
  expect(parseSlash("/CHECKINS")).toEqual({ kind: "unknown", name: "checkins" });
});
