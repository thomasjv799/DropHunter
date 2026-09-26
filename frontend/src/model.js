export const formatMoney = (value) =>
  value == null
    ? "Not checked"
    : new Intl.NumberFormat("en-IN", {
        style: "currency",
        currency: "INR",
        maximumFractionDigits: 2,
        minimumFractionDigits: 0,
      }).format(Number(value));
export function priceStatus(game, now = Date.now()) {
  if (game.price == null || !game.fetched_at) return "unknown";
  if (now - Date.parse(game.fetched_at) > 86400000) return "stale";
  return game.target_price != null &&
    Number(game.price) <= Number(game.target_price)
    ? "deal"
    : "watching";
}
export function chartSegments(points) {
  const segments = [];
  for (const point of points) {
    const last = segments.at(-1);
    if (
      !last ||
      Date.parse(point.fetched_at) - Date.parse(last.at(-1).fetched_at) >
        86400000 * 1.5
    )
      segments.push([point]);
    else last.push(point);
  }
  return segments;
}
export function createGeneration() {
  let generation = 0;
  return {
    current: () => generation,
    advance: () => ++generation,
    isCurrent: (value) => value === generation,
  };
}
