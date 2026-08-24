import type { StateMachine } from '../core/types';

export const vendingMachine: StateMachine = {
  states: [
    { id: 'idle', name: '待機', position: { x: 40, y: 150 }, initial: true },
    { id: 'paid', name: '入金済み', position: { x: 260, y: 60 } },
    { id: 'selected', name: '商品選択', position: { x: 480, y: 60 } },
    { id: 'dispensing', name: '払出中', position: { x: 480, y: 240 } },
  ],
  transitions: [
    { id: 'coin', from: 'idle', to: 'paid', event: 'coin' },
    { id: 'select', from: 'paid', to: 'selected', event: 'select' },
    { id: 'return', from: 'paid', to: 'idle', event: 'return' },
    { id: 'dispense', from: 'selected', to: 'dispensing', event: 'dispense' },
    { id: 'cancel', from: 'selected', to: 'idle', event: 'cancel' },
    { id: 'finish', from: 'dispensing', to: 'idle', event: 'finish' },
  ],
};
