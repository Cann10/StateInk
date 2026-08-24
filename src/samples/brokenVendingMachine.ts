import type { StateMachine } from '../core/types';

export const brokenVendingMachine: StateMachine = {
  states: [
    { id: 'idle', name: '待機', position: { x: 30, y: 150 }, initial: true },
    { id: 'paid', name: '入金済み', position: { x: 220, y: 60 } },
    { id: 'selected', name: '商品選択', position: { x: 410, y: 60 } },
    { id: 'sold-out', name: '売り切れ', position: { x: 600, y: 60 } },
  ],
  transitions: [
    { id: 'coin', from: 'idle', to: 'paid', event: 'coin' },
    { id: 'select', from: 'paid', to: 'selected', event: 'select' },
    { id: 'return', from: 'paid', to: 'idle', event: 'return' },
    { id: 'sold-out', from: 'selected', to: 'sold-out', event: 'sold_out' },
  ],
};
