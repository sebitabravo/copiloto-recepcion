// Funciones puras del plano y del dashboard (landing/demo-occupancy.js), sin navegador.
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const source = readFileSync(new URL('../landing/demo-occupancy.js', import.meta.url), 'utf8');
const window = {};
vm.runInNewContext(source, {window, Intl, Date, Number, Math, String, Map, Object, Array});
const {buildPlan, computeKpis} = window.DemoOccupancy;
// Los arrays creados dentro de vm son de otro realm: se normalizan antes de deepStrictEqual.
const plain = value => JSON.parse(JSON.stringify(value));

const units = [
  {room_id: 1, number: '101', code: 'sdvj', short: 'SDVJ', name: 'Single', nightly_price_clp: 65000},
  {room_id: 2, number: '102', code: 'sdvj', short: 'SDVJ', name: 'Single', nightly_price_clp: 65000},
  {room_id: 3, number: '103', code: 'dvp', short: 'DVP', name: 'Doble', nightly_price_clp: 70000}
];
const booking = (id, room, checkin, checkout, extra = {}) => ({
  booking_id: id, room_id: room, guest_name: 'Ana María Pérez', checkin, checkout, adults: 2, children: 0, source: 'personal', ...extra
});
const base = {start: '2026-11-16', days: 14, units, bookings: []};

test('buildPlan builds one column per day with weekends marked', () => {
  const plan = buildPlan(base);
  assert.equal(plan.columns.length, 14);
  assert.equal(plan.columns[0].iso, '2026-11-16');
  assert.equal(plan.columns[0].weekday, 'lun');
  assert.deepEqual(plain(plan.columns.filter(c => c.weekend).map(c => c.iso)),
    ['2026-11-21', '2026-11-22', '2026-11-28', '2026-11-29']);
  assert.equal(plan.rows.length, 3);
  assert.ok(plan.rows.every(row => row.bars.length === 0));
});

test('buildPlan places a stay on its nights and frees the checkout day', () => {
  const plan = buildPlan({...base, bookings: [booking(7, 1, '2026-11-18', '2026-11-21')]});
  const [bar] = plan.rows[0].bars;
  assert.equal(bar.column, 2);
  assert.equal(bar.span, 3);
  assert.equal(bar.cutStart, false);
  assert.equal(bar.cutEnd, false);
  assert.equal(bar.label, '2 Pérez');
});

test('buildPlan clips a stay that crosses the start of the range', () => {
  const [bar] = buildPlan({...base, bookings: [booking(1, 1, '2026-11-13', '2026-11-18')]}).rows[0].bars;
  assert.equal(bar.column, 0);
  assert.equal(bar.span, 2);
  assert.equal(bar.cutStart, true);
});

test('buildPlan clips a stay that crosses the end of the range', () => {
  const [bar] = buildPlan({...base, bookings: [booking(1, 1, '2026-11-28', '2026-12-04')]}).rows[0].bars;
  assert.equal(bar.column, 12);
  assert.equal(bar.span, 2);
  assert.equal(bar.cutEnd, true);
});

test('buildPlan ignores stays outside the range, including a checkout on the first day', () => {
  const plan = buildPlan({...base, bookings: [
    booking(1, 1, '2026-11-10', '2026-11-16'),
    booking(2, 1, '2026-11-30', '2026-12-02'),
    booking(3, 99, '2026-11-17', '2026-11-18')
  ]});
  assert.equal(plan.rows[0].bars.length, 0);
  assert.ok(plan.rows.every(row => row.bars.length === 0));
});

test('buildPlan handles an empty range and sorts bars within a unit', () => {
  assert.deepEqual(plain(buildPlan({...base, days: 0}).columns), []);
  const plan = buildPlan({...base, bookings: [booking(2, 1, '2026-11-25', '2026-11-27'), booking(1, 1, '2026-11-17', '2026-11-19')]});
  assert.deepEqual(plain(plan.rows[0].bars.map(bar => bar.booking.booking_id)), [1, 2]);
});

test('computeKpis counts arrivals, departures and people in house', () => {
  const kpis = computeKpis({...base, bookings: [
    booking(1, 1, '2026-11-16', '2026-11-18', {adults: 2, children: 1, source: 'ia'}),
    booking(2, 2, '2026-11-14', '2026-11-16'),
    booking(3, 3, '2026-11-15', '2026-11-17')
  ]}, '2026-11-16');
  assert.equal(kpis.total, 3);
  assert.equal(kpis.occupied, 2);
  assert.equal(kpis.occupancyPct, 67);
  assert.equal(kpis.arrivals, 1);
  assert.equal(kpis.departures, 1);
  assert.equal(kpis.inHouse, 5);
  assert.deepEqual(plain(kpis.bySource), {ia: 1, personal: 1}, 'la que sale hoy ya no cuenta');
});

test('computeKpis reports per-day and per-type occupancy', () => {
  const kpis = computeKpis({...base, days: 2, bookings: [booking(1, 1, '2026-11-16', '2026-11-18')]}, '2026-11-16');
  assert.deepEqual(plain(kpis.perDay.map(day => day.occupied)), [1, 1]);
  assert.deepEqual(plain(kpis.perDay.map(day => day.pct)), [33, 33]);
  const sdvj = kpis.types.find(type => type.code === 'sdvj');
  assert.equal(sdvj.units, 2);
  assert.equal(sdvj.nights, 2);
  assert.equal(sdvj.pct, 50);
  assert.equal(kpis.types.find(type => type.code === 'dvp').pct, 0);
});

test('computeKpis counts departures today when the range starts yesterday and totals start today', () => {
  const kpis = computeKpis({...base, start: '2026-11-15', days: 15, bookings: [
    booking(1, 1, '2026-11-13', '2026-11-16', {source: 'ia'}),
    booking(2, 2, '2026-11-15', '2026-11-17'),
    booking(3, 3, '2026-11-12', '2026-11-15')
  ]}, '2026-11-16');
  assert.equal(kpis.departures, 1);
  assert.equal(kpis.occupied, 1);
  assert.equal(kpis.perDay.length, 14);
  assert.equal(kpis.perDay[0].iso, '2026-11-16');
  assert.deepEqual(plain(kpis.bySource), {ia: 0, personal: 1}, 'lo que ya salió no cuenta');
});

test('computeKpis does not divide by zero without units or days', () => {
  const kpis = computeKpis({start: '2026-11-16', days: 0, units: [], bookings: []}, '2026-11-16');
  assert.equal(kpis.occupancyPct, 0);
  assert.deepEqual(plain(kpis.perDay), []);
  assert.deepEqual(plain(kpis.types), []);
});

test('the occupancy view never interprets server text as HTML', () => {
  assert.doesNotMatch(source, /innerHTML|insertAdjacentHTML/);
});
