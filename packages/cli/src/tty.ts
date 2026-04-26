const ENABLED = process.stdout.isTTY && process.env.NO_COLOR !== "1";

export function color(open: number, close: number, text: string): string {
  if (!ENABLED) return text;
  return `\x1b[${open}m${text}\x1b[${close}m`;
}

export const dim = (t: string) => color(2, 22, t);
export const bold = (t: string) => color(1, 22, t);
export const green = (t: string) => color(32, 39, t);
export const red = (t: string) => color(31, 39, t);
export const yellow = (t: string) => color(33, 39, t);
export const cyan = (t: string) => color(36, 39, t);
