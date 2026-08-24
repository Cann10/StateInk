import { describe, expect, it } from 'vitest';
import { vendingMachine } from '../../samples/vendingMachine';
import { machineToJson, machineToSvg } from './exportMachine';

describe('machine export', () => {
  it('exports reloadable JSON', () => {
    expect(JSON.parse(machineToJson(vendingMachine))).toEqual(vendingMachine);
  });

  it('exports a standalone SVG with state and transition labels', () => {
    const svg = machineToSvg(vendingMachine);
    expect(svg).toContain('<svg xmlns="http://www.w3.org/2000/svg"');
    expect(svg).toContain('coin');
    expect(svg).toContain('待機');
  });
});
