import { beatOpacity } from "./FilmHero";

test("a title is fully visible at its centre and gone far from it", () => {
  expect(beatOpacity(0.48, 0.48)).toBe(1);
  expect(beatOpacity(0.9, 0.48)).toBe(0);
  const half = beatOpacity(0.6, 0.48);
  expect(half).toBeGreaterThan(0);
  expect(half).toBeLessThan(1);
});

test("the first title is there at the top, the last stays until the end", () => {
  expect(beatOpacity(0, 0.12, true)).toBe(1);
  expect(beatOpacity(1, 0.84, false, true)).toBe(1);
  expect(beatOpacity(0, 0.12)).toBeLessThan(1);
});
