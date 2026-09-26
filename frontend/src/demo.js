const names = [
  "EVERSPACE 2",
  "Elden Ring",
  "Hades",
  "Baldur’s Gate 3",
  "Cyberpunk 2077",
  "Hollow Knight",
  "Celeste",
  "Stardew Valley",
  "Red Dead Redemption 2",
  "Disco Elysium",
  "Control",
  "Alan Wake 2",
  "DOOM Eternal",
  "Forza Horizon 5",
  "Death Stranding",
  "The Witcher 3",
  "Sekiro",
  "Dark Souls III",
  "Armored Core VI",
  "Resident Evil 4",
];
let games = Array.from({ length: 100 }, (_, i) => ({
  id: String(i),
  title: i < names.length ? names[i] : `Sample game ${i + 1}`,
  price: i % 17 === 0 ? null : 199 + ((i * 137) % 3500),
  target_price: i % 9 === 0 ? null : 500 + ((i * 103) % 2500),
  store: ["Steam", "GOG", "Epic"][i % 3],
  fetched_at:
    i % 17 === 0
      ? null
      : new Date(Date.now() - (i % 13 === 0 ? 48 : 2) * 3600000).toISOString(),
}));
let email = "";
export async function demoRequest(path, options = {}) {
  const url = new URL(path, "https://demo.invalid"),
    params = url.searchParams;
  const data = options.body ? JSON.parse(options.body) : {};
  if (path === "/me") return { email: "Demo workspace" };
  if (path === "/summary")
    return {
      games: games.length,
      at_target: games.filter(
        (g) =>
          g.price != null &&
          g.target_price != null &&
          g.price <= g.target_price,
      ).length,
      unknown: games.filter((g) => g.price == null).length,
      stale: games.filter(
        (g) => g.fetched_at && Date.now() - Date.parse(g.fetched_at) > 86400000,
      ).length,
      last_observed: new Date().toISOString(),
    };
  if (url.pathname === "/games" && !options.method) {
    const q = (params.get("q") || "").toLowerCase(),
      status = params.get("status"),
      sort = params.get("sort"),
      page = Number(params.get("page") || 1),
      limit = 10;
    const rows = games
      .filter((g) => g.title.toLowerCase().includes(q))
      .filter((g) =>
        status === "deal"
          ? g.price != null &&
            g.target_price != null &&
            g.price <= g.target_price
          : status === "unknown"
            ? g.price == null
            : status === "watching"
              ? g.target_price == null ||
                (g.price != null && g.price > g.target_price)
              : true,
      )
      .sort((a, b) =>
        sort === "price"
          ? (a.price ?? Infinity) - (b.price ?? Infinity)
          : sort === "gap"
            ? (a.price != null && a.target_price != null
                ? a.price - a.target_price
                : Infinity) -
              (b.price != null && b.target_price != null
                ? b.price - b.target_price
                : Infinity)
            : a.title.localeCompare(b.title),
      );
    return {
      items: rows.slice((page - 1) * limit, page * limit),
      total: rows.length,
      limit,
      page,
    };
  }
  if (url.pathname.match(/^\/games\/[^/]+\/history$/)) {
    const game = games.find((g) => g.id === url.pathname.split("/")[2]),
      days = Number(params.get("days") || 30);
    const points =
      game.price == null
        ? []
        : Array.from({ length: days * 2 }, (_, i) => ({
            price: game.price + Math.floor((days * 2 - i) / 8) * 80,
            regular_price: game.price + 1500,
            store: i < days ? "GOG" : game.store,
            fetched_at: new Date(
              Date.now() - (days * 2 - 1 - i) * 43200000,
            ).toISOString(),
          }));
    return { game, points };
  }
  if (path.startsWith("/games/") && options.method === "PATCH") {
    games.find((g) => g.id === path.split("/")[2]).target_price =
      data.target_price;
    return { ok: true };
  }
  if (path.startsWith("/games/") && options.method === "DELETE") {
    games = games.filter((g) => g.id !== path.split("/")[2]);
    return { ok: true };
  }
  if (path === "/search") return { title: data.title, selection: data.title };
  if (path === "/games" && options.method === "POST") {
    if (games.length >= 100)
      throw new Error(
        "You can track up to 100 games. Remove one to try adding another.",
      );
    const game = {
      id: crypto.randomUUID(),
      title: data.selection,
      target_price: data.target_price,
      price: null,
    };
    games.push(game);
    return game;
  }
  if (path === "/activity")
    return {
      items: [
        {
          title: "Elden Ring",
          price: 499,
          notified_at: new Date().toISOString(),
        },
      ],
    };
  if (path === "/watches")
    return {
      items: [
        {
          name: "Sample field watch",
          brand: "Demo",
          target_price: 15000,
          price: 18500,
          fetched_at: new Date().toISOString(),
        },
      ],
    };
  if (path === "/settings") {
    if (options.method) email = data.email;
    return { email };
  }
  throw new Error("Unknown demo operation");
}
