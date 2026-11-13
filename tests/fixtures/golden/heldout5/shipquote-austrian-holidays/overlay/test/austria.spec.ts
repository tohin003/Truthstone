// Austrian delivery calendar (Lena). Written for vitest, which the checkout service's repo uses.
import { describe, expect, it } from "vitest";
import { addBusinessDays, deliveryDate, holidays, isBusinessDay } from "../src/calendar.ts";

describe("Austrian public holidays", () => {
  it("lists the thirteen national holidays in date order", () => {
    expect(holidays(2026, "AT").map((h) => h.date)).toEqual([
      "2026-01-01", "2026-01-06", "2026-04-06", "2026-05-01", "2026-05-14", "2026-05-25",
      "2026-06-04", "2026-08-15", "2026-10-26", "2026-11-01", "2026-12-08", "2026-12-25",
      "2026-12-26",
    ]);
  });

  it("keeps Germany's list as the default", () => {
    expect(holidays(2026)).toEqual(holidays(2026, "DE"));
    expect(holidays(2026).map((h) => h.date)).toContain("2026-10-03");
  });

  it("treats German-only holidays as business days in Austria", () => {
    expect(isBusinessDay("2026-04-03", "AT")).toBe(true); // Good Friday
    expect(isBusinessDay("2025-10-03", "AT")).toBe(true); // German Unity Day
    expect(isBusinessDay("2026-10-26", "AT")).toBe(false);
    expect(addBusinessDays("2026-06-03", 1, "AT")).toBe("2026-06-05");
  });
});

describe("delivery estimates to Austria", () => {
  it("counts transit on the Austrian calendar", () => {
    expect(deliveryDate("2026-04-02", 4)).toBe("2026-04-08");
    expect(deliveryDate("2026-10-23", 4)).toBe("2026-10-29");
  });

  it("leaves German zones on the German calendar", () => {
    expect(deliveryDate("2026-10-23", 1)).toBe("2026-10-26");
    expect(deliveryDate("2026-04-02", 1)).toBe("2026-04-07");
  });
});
