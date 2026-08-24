import type { StateMachine } from '../../core/types';

const escapeXml = (value: string) => value.replace(/[<>&"']/g, (character) => ({
  '<': '&lt;', '>': '&gt;', '&': '&amp;', '"': '&quot;', "'": '&apos;',
})[character] ?? character);

export function machineToJson(machine: StateMachine): string {
  return `${JSON.stringify(machine, null, 2)}\n`;
}

export function machineToSvg(machine: StateMachine): string {
  const padding = 90;
  const nodeWidth = 160;
  const nodeHeight = 62;
  const maxX = Math.max(520, ...machine.states.map((state) => state.position.x + nodeWidth + padding));
  const maxY = Math.max(320, ...machine.states.map((state) => state.position.y + nodeHeight + padding));
  const byId = new Map(machine.states.map((state) => [state.id, state]));
  const transitions = machine.transitions.map((transition) => {
    const from = byId.get(transition.from);
    const to = byId.get(transition.to);
    if (!from || !to) return '';
    const x1 = from.position.x + nodeWidth / 2;
    const y1 = from.position.y + nodeHeight / 2;
    const x2 = to.position.x + nodeWidth / 2;
    const y2 = to.position.y + nodeHeight / 2;
    const labelX = (x1 + x2) / 2;
    const labelY = (y1 + y2) / 2 - 8;
    return `<g><line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#73827a" stroke-width="2" marker-end="url(#arrow)"/><text x="${labelX}" y="${labelY}" text-anchor="middle">${escapeXml(transition.event)}</text></g>`;
  }).join('');
  const states = machine.states.map((state) => `<g transform="translate(${state.position.x} ${state.position.y})"><rect width="${nodeWidth}" height="${nodeHeight}" rx="10" fill="#fff" stroke="${state.initial ? '#0f5a43' : '#c8d4cd'}" stroke-width="${state.initial ? 3 : 2}"/><text x="80" y="36" text-anchor="middle" font-weight="700">${state.initial ? '▶ ' : ''}${escapeXml(state.name)}${state.final ? ' ◎' : ''}</text></g>`).join('');
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${maxX}" height="${maxY}" viewBox="0 0 ${maxX} ${maxY}"><defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="9" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#73827a"/></marker></defs><rect width="100%" height="100%" fill="#f7f8f4"/><g font-family="Inter, Noto Sans JP, sans-serif" font-size="13" fill="#17211c">${transitions}${states}</g></svg>`;
}

export function downloadText(filename: string, content: string, type: string): void {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export async function downloadPng(machine: StateMachine): Promise<void> {
  const svg = machineToSvg(machine);
  const svgUrl = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml;charset=utf-8' }));
  try {
    const image = new Image();
    image.src = svgUrl;
    await image.decode();
    const canvas = document.createElement('canvas');
    canvas.width = image.naturalWidth * 2;
    canvas.height = image.naturalHeight * 2;
    const context = canvas.getContext('2d');
    if (!context) throw new Error('PNGを作成できませんでした');
    context.scale(2, 2);
    context.drawImage(image, 0, 0);
    const blob = await new Promise<Blob>((resolve, reject) => canvas.toBlob((value) => value ? resolve(value) : reject(new Error('PNGを作成できませんでした')), 'image/png'));
    const pngUrl = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = pngUrl;
    anchor.download = 'stateink-diagram.png';
    anchor.click();
    URL.revokeObjectURL(pngUrl);
  } finally {
    URL.revokeObjectURL(svgUrl);
  }
}
