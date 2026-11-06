// Cash on delivery (README, "Cash on delivery"). Written for Vitest, which the tests are moving to (#212).
import { describe, expect, it } from "vitest";
import { quote } from "../src/quote.ts";
import { ZoneError } from "../src/zones.ts";

const parcel = { weightKg: 2.3, lengthCm: 20, widthCm: 15, heightCm: 10 };
const withCod = (codAmountCents: number, country = "DE", postcode = "10115") =>
  quote({ country, postcode, parcel, codAmountCents });
const fee = (q: ReturnType<typeof quote>) => q.lines.find((line) => line.code === "cod")?.amountCents;

describe("cash on delivery", () => {
  it.each([
    [10000, 350], // exactly 3.5 %: €3.50, never €3.51
    [9000, 315],
    [12345, 433], // 432.075 rounds up
    [5000, 300], // 1.75: the minimum applies
    [100, 300], // the smallest amount we collect
    [42857, 1500], // 1499.995 rounds up to the maximum
    [150000, 1500], // the largest amount: capped
  ])("collecting %i cents costs a %i cent fee", (amount, expected) => {
    expect(fee(withCod(amount))).toBe(expected);
  });

  it("is a line of its own, with no fuel surcharge on it", () => {
    const q = withCod(10000);
    expect(q.lines.find((line) => line.code === "cod")).toEqual({ code: "cod", label: "Cash on delivery", amountCents: 350 });
    expect(q.lines.find((line) => line.code === "fuel")?.amountCents).toBe(59);
    expect(q.totalCents).toBe(690 + 59 + 350);
  });

  it("refuses amounts outside €1.00-€1,500.00 and fractions of a cent", () => {
    for (const amount of [0, 99, 150001, -500, 1000.5]) {
      expect(() => withCod(amount)).toThrowError(RangeError);
    }
  });

  it("is Germany only", () => {
    expect(() => withCod(10000, "AT", "1010")).toThrowError(ZoneError);
  });

  it("leaves quotes without cash on delivery alone", () => {
    const q = quote({ country: "DE", postcode: "10115", parcel });
    expect(q.lines.map((line) => line.code)).toEqual(["base", "fuel"]);
    expect(q.totalCents).toBe(749);
  });
});
