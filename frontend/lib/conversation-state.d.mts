export type StoredTurn = { role: string; content: string; [key: string]: unknown };
export function restoreConversation(storage: Pick<Storage, "getItem">, key: string): StoredTurn[];
export function persistConversation(storage: Pick<Storage, "setItem">, key: string, turns: StoredTurn[]): boolean;
