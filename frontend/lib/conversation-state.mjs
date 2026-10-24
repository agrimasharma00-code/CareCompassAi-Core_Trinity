export function restoreConversation(storage, key) {
  try {
    const turns = JSON.parse(storage.getItem(key) || "[]");
    return Array.isArray(turns) ? turns.filter((turn) => turn && typeof turn.role === "string" && typeof turn.content === "string") : [];
  } catch {
    return [];
  }
}

export function persistConversation(storage, key, turns) {
  try {
    storage.setItem(key, JSON.stringify(turns));
    return true;
  } catch {
    return false;
  }
}
