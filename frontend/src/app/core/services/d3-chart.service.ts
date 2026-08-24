import { Injectable } from '@angular/core';
import * as d3 from 'd3';

export interface BarData { label: string; value: number; }
export interface GroupedBarData { label: string; income: number; expenses: number; }
export interface DonutData { label: string; value: number; color: string; }
export interface AreaData { day: number; value: number; }

const FMT = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', maximumFractionDigits: 0 });
const FMT2 = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });

@Injectable({ providedIn: 'root' })
export class D3ChartService {

  /** Grouped bar (income + expenses) with balance area line */
  renderGroupedBar(el: HTMLElement, data: GroupedBarData[]): void {
    d3.select(el).selectAll('*').remove();
    const W = el.clientWidth || 600, H = el.clientHeight || 280;
    const margin = { top: 20, right: 20, bottom: 30, left: 70 };
    const w = W - margin.left - margin.right;
    const h = H - margin.top - margin.bottom;

    const svg = d3.select(el).append('svg').attr('width', W).attr('height', H)
      .append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    const x0 = d3.scaleBand().domain(data.map(d => d.label)).range([0, w]).padding(0.25);
    const x1 = d3.scaleBand().domain(['income', 'expenses']).range([0, x0.bandwidth()]).padding(0.05);
    const maxY = d3.max(data, d => Math.max(d.income, d.expenses)) ?? 0;
    const y = d3.scaleLinear().domain([0, maxY * 1.1]).range([h, 0]);

    // Gridlines
    svg.append('g').attr('class', 'grid')
      .call(d3.axisLeft(y).tickSize(-w).tickFormat(() => ''))
      .call(g => { g.select('.domain').remove(); g.selectAll('line').attr('stroke', 'rgba(0,0,0,0.06)'); });

    // Income bars
    svg.selectAll('.bar-income').data(data).enter().append('rect')
      .attr('x', d => (x0(d.label) ?? 0) + (x1('income') ?? 0))
      .attr('y', d => y(d.income))
      .attr('width', x1.bandwidth())
      .attr('height', d => h - y(d.income))
      .attr('fill', '#05b169').attr('rx', 3)
      .append('title').text(d => `Receita: ${FMT2.format(d.income)}`);

    // Expense bars
    svg.selectAll('.bar-exp').data(data).enter().append('rect')
      .attr('x', d => (x0(d.label) ?? 0) + (x1('expenses') ?? 0))
      .attr('y', d => y(d.expenses))
      .attr('width', x1.bandwidth())
      .attr('height', d => h - y(d.expenses))
      .attr('fill', '#cf202f').attr('rx', 3)
      .append('title').text(d => `Despesa: ${FMT2.format(d.expenses)}`);

    // Balance area
    const balanceData = data.map(d => ({ label: d.label, balance: d.income - d.expenses }));
    const minBal = d3.min(balanceData, d => d.balance) ?? 0;
    const maxBal = d3.max(balanceData, d => d.balance) ?? 0;
    if (maxBal !== minBal) {
      const yBal = d3.scaleLinear().domain([Math.min(0, minBal) * 1.2, Math.max(0, maxBal) * 1.2]).range([h, 0]);
      const line = d3.line<{ label: string; balance: number }>()
        .x(d => (x0(d.label) ?? 0) + x0.bandwidth() / 2)
        .y(d => yBal(d.balance))
        .curve(d3.curveMonotoneX);
      svg.append('path').datum(balanceData).attr('fill', 'none')
        .attr('stroke', '#f4b000').attr('stroke-width', 2).attr('stroke-dasharray', '4,2')
        .attr('d', line);
      // Dots
      svg.selectAll('.bal-dot').data(balanceData).enter().append('circle')
        .attr('cx', d => (x0(d.label) ?? 0) + x0.bandwidth() / 2)
        .attr('cy', d => yBal(d.balance))
        .attr('r', 3).attr('fill', '#f4b000')
        .append('title').text(d => `Saldo: ${FMT2.format(d.balance)}`);
    }

    // Axes
    svg.append('g').attr('transform', `translate(0,${h})`).call(d3.axisBottom(x0).tickSize(0))
      .call(g => g.select('.domain').attr('stroke', 'rgba(0,0,0,0.15)'));
    svg.append('g').call(d3.axisLeft(y).ticks(5).tickFormat(v => FMT.format(+v)))
      .call(g => g.select('.domain').remove());

    // Legend
    const lg = svg.append('g').attr('transform', `translate(${w - 200}, -14)`);
    [{ c: '#05b169', t: 'Receitas' }, { c: '#cf202f', t: 'Despesas' }, { c: '#f4b000', t: 'Saldo' }]
      .forEach((item, i) => {
        const gx = i * 68;
        lg.append('rect').attr('x', gx).attr('y', 0).attr('width', 10).attr('height', 10).attr('fill', item.c).attr('rx', 2);
        lg.append('text').attr('x', gx + 14).attr('y', 9).text(item.t)
          .attr('font-size', '11px').attr('fill', '#5b616e');
      });
  }

  /** Horizontal bar chart */
  renderHorizontalBar(el: HTMLElement, data: BarData[], color = '#0052ff'): void {
    d3.select(el).selectAll('*').remove();
    if (!data.length) return;
    const W = el.clientWidth || 500, H = Math.max(data.length * 44 + 40, 120);
    el.style.height = H + 'px';
    const margin = { top: 10, right: 80, bottom: 20, left: 140 };
    const w = W - margin.left - margin.right;
    const h = H - margin.top - margin.bottom;

    const svg = d3.select(el).append('svg').attr('width', W).attr('height', H)
      .append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    const y = d3.scaleBand().domain(data.map(d => d.label)).range([0, h]).padding(0.3);
    const x = d3.scaleLinear().domain([0, d3.max(data, d => d.value) ?? 0]).range([0, w]);

    svg.selectAll('.bar').data(data).enter().append('rect')
      .attr('y', d => y(d.label) ?? 0).attr('x', 0)
      .attr('height', y.bandwidth()).attr('width', d => x(d.value))
      .attr('fill', color).attr('rx', 4)
      .append('title').text(d => `${d.label}: ${FMT2.format(d.value)}`);

    // Value labels
    svg.selectAll('.val-label').data(data).enter().append('text')
      .attr('x', d => x(d.value) + 6)
      .attr('y', d => (y(d.label) ?? 0) + y.bandwidth() / 2 + 4)
      .text(d => FMT.format(d.value))
      .attr('font-size', '11px').attr('fill', '#5b616e');

    svg.append('g').call(d3.axisLeft(y).tickSize(0).tickPadding(8))
      .call(g => { g.select('.domain').remove(); g.selectAll('text').attr('font-size', '12px'); });
    svg.append('g').attr('transform', `translate(0,${h})`).call(d3.axisBottom(x).ticks(4).tickFormat(v => FMT.format(+v)))
      .call(g => g.select('.domain').attr('stroke', 'rgba(0,0,0,0.1)'));
  }

  /** Donut chart with center total label */
  renderDonut(el: HTMLElement, data: DonutData[], centerLabel = ''): void {
    d3.select(el).selectAll('*').remove();
    if (!data.length) return;
    const size = Math.min(el.clientWidth || 260, el.clientHeight || 260);
    const r = size / 2;
    const ir = r * 0.62;

    const svg = d3.select(el).append('svg').attr('width', el.clientWidth || 260).attr('height', size)
      .append('g').attr('transform', `translate(${r},${r})`);

    const pie = d3.pie<DonutData>().value(d => d.value).sort(null);
    const arc = d3.arc<d3.PieArcDatum<DonutData>>().innerRadius(ir).outerRadius(r - 4);
    const arcHover = d3.arc<d3.PieArcDatum<DonutData>>().innerRadius(ir).outerRadius(r);

    const arcs = svg.selectAll('.arc').data(pie(data)).enter().append('g');
    arcs.append('path').attr('d', arc).attr('fill', d => d.data.color).attr('stroke', '#fff').attr('stroke-width', 2)
      .on('mouseenter', function(_, d) { d3.select(this).attr('d', arcHover(d) ?? ''); })
      .on('mouseleave', function(_, d) { d3.select(this).attr('d', arc(d) ?? ''); })
      .append('title').text(d => `${d.data.label}: ${FMT2.format(d.data.value)}`);

    // Center label
    if (centerLabel) {
      svg.append('text').attr('text-anchor', 'middle').attr('dy', '-0.3em')
        .attr('font-size', '11px').attr('fill', '#7c828a').text('Total');
      svg.append('text').attr('text-anchor', 'middle').attr('dy', '1.1em')
        .attr('font-size', '14px').attr('font-weight', '600').attr('fill', '#16181c').text(centerLabel);
    }
  }

  /** Simple vertical bar chart with optional average line */
  renderBar(el: HTMLElement, data: BarData[], opts?: { color?: string; highlightLast?: boolean; showAvgLine?: boolean }): void {
    d3.select(el).selectAll('*').remove();
    if (!data.length) return;
    const W = el.clientWidth || 500, H = el.clientHeight || 220;
    const margin = { top: 16, right: 16, bottom: 30, left: 64 };
    const w = W - margin.left - margin.right;
    const h = H - margin.top - margin.bottom;

    const svg = d3.select(el).append('svg').attr('width', W).attr('height', H)
      .append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    const x = d3.scaleBand().domain(data.map(d => d.label)).range([0, w]).padding(0.25);
    const y = d3.scaleLinear().domain([0, (d3.max(data, d => d.value) ?? 0) * 1.12]).range([h, 0]);

    // Gridlines
    svg.append('g').call(d3.axisLeft(y).tickSize(-w).tickFormat(() => ''))
      .call(g => { g.select('.domain').remove(); g.selectAll('line').attr('stroke', 'rgba(0,0,0,0.05)'); });

    const baseColor = opts?.color ?? '#0052ff';
    const currentMonth = new Date().getMonth();
    svg.selectAll('.bar').data(data).enter().append('rect')
      .attr('x', d => x(d.label) ?? 0).attr('y', d => y(d.value))
      .attr('width', x.bandwidth()).attr('height', d => h - y(d.value))
      .attr('fill', (d, i) => (opts?.highlightLast && i === data.length - 1) ? baseColor : (opts?.highlightLast ? baseColor + '60' : baseColor))
      .attr('rx', 4)
      .append('title').text(d => `${d.label}: ${FMT2.format(d.value)}`);

    // Average line
    if (opts?.showAvgLine) {
      const nonZero = data.filter(d => d.value > 0);
      if (nonZero.length) {
        const avg = nonZero.reduce((s, d) => s + d.value, 0) / nonZero.length;
        svg.append('line').attr('x1', 0).attr('x2', w).attr('y1', y(avg)).attr('y2', y(avg))
          .attr('stroke', '#f4b000').attr('stroke-width', 1.5).attr('stroke-dasharray', '6,3');
        svg.append('text').attr('x', w + 4).attr('y', y(avg) + 4)
          .attr('font-size', '10px').attr('fill', '#f4b000').text('Média');
      }
    }

    svg.append('g').attr('transform', `translate(0,${h})`).call(d3.axisBottom(x).tickSize(0).tickPadding(6))
      .call(g => { g.select('.domain').attr('stroke', 'rgba(0,0,0,0.1)'); g.selectAll('text').attr('font-size', '11px'); });
    svg.append('g').call(d3.axisLeft(y).ticks(5).tickFormat(v => FMT.format(+v)))
      .call(g => g.select('.domain').remove());
  }

  /** Area chart with gradient fill */
  renderArea(el: HTMLElement, data: AreaData[], color = '#0052ff'): void {
    d3.select(el).selectAll('*').remove();
    if (!data.length) return;
    const W = el.clientWidth || 600, H = el.clientHeight || 220;
    const margin = { top: 16, right: 16, bottom: 30, left: 70 };
    const w = W - margin.left - margin.right;
    const h = H - margin.top - margin.bottom;

    const svg = d3.select(el).append('svg').attr('width', W).attr('height', H)
      .append('g').attr('transform', `translate(${margin.left},${margin.top})`);

    const x = d3.scaleLinear().domain([d3.min(data, d => d.day) ?? 1, d3.max(data, d => d.day) ?? 31]).range([0, w]);
    const y = d3.scaleLinear().domain([0, (d3.max(data, d => d.value) ?? 0) * 1.15]).range([h, 0]);

    // Gradient
    const gradId = 'area-grad-' + Math.random().toString(36).slice(2);
    const defs = svg.append('defs');
    const grad = defs.append('linearGradient').attr('id', gradId).attr('x1', 0).attr('x2', 0).attr('y1', 0).attr('y2', 1);
    grad.append('stop').attr('offset', '0%').attr('stop-color', color).attr('stop-opacity', 0.35);
    grad.append('stop').attr('offset', '100%').attr('stop-color', color).attr('stop-opacity', 0.02);

    // Gridlines
    svg.append('g').call(d3.axisLeft(y).tickSize(-w).tickFormat(() => ''))
      .call(g => { g.select('.domain').remove(); g.selectAll('line').attr('stroke', 'rgba(0,0,0,0.05)'); });

    const area = d3.area<AreaData>().x(d => x(d.day)).y0(h).y1(d => y(d.value)).curve(d3.curveMonotoneX);
    const line = d3.line<AreaData>().x(d => x(d.day)).y(d => y(d.value)).curve(d3.curveMonotoneX);

    svg.append('path').datum(data).attr('fill', `url(#${gradId})`).attr('d', area);
    svg.append('path').datum(data).attr('fill', 'none').attr('stroke', color).attr('stroke-width', 2).attr('d', line);

    // Dots on non-zero
    svg.selectAll('.dot').data(data.filter(d => d.value > 0)).enter().append('circle')
      .attr('cx', d => x(d.day)).attr('cy', d => y(d.value)).attr('r', 3)
      .attr('fill', color).attr('stroke', '#fff').attr('stroke-width', 1.5)
      .append('title').text(d => `Dia ${d.day}: ${FMT2.format(d.value)}`);

    svg.append('g').attr('transform', `translate(0,${h})`).call(d3.axisBottom(x).ticks(8).tickFormat(d => `Dia ${+d}`))
      .call(g => { g.select('.domain').attr('stroke', 'rgba(0,0,0,0.1)'); g.selectAll('text').attr('font-size', '11px'); });
    svg.append('g').call(d3.axisLeft(y).ticks(5).tickFormat(v => FMT.format(+v)))
      .call(g => g.select('.domain').remove());
  }

  /** Treemap for category distribution */
  renderTreemap(el: HTMLElement, data: DonutData[]): void {
    d3.select(el).selectAll('*').remove();
    if (!data.length) return;
    const W = el.clientWidth || 400, H = el.clientHeight || 220;

    const svg = d3.select(el).append('svg').attr('width', W).attr('height', H);
    const root = d3.hierarchy({ children: data } as any)
      .sum((d: any) => d.value ?? 0)
      .sort((a, b) => (b.value ?? 0) - (a.value ?? 0));

    d3.treemap<any>().size([W, H]).padding(3).round(true)(root);

    const cells = svg.selectAll('g').data(root.leaves()).enter().append('g')
      .attr('transform', (d: any) => `translate(${d.x0},${d.y0})`);

    cells.append('rect')
      .attr('width', (d: any) => d.x1 - d.x0).attr('height', (d: any) => d.y1 - d.y0)
      .attr('fill', (d: any) => d.data.color).attr('rx', 4)
      .append('title').text((d: any) => `${d.data.label}: ${FMT2.format(d.data.value)}`);

    cells.filter((d: any) => (d.x1 - d.x0) > 50 && (d.y1 - d.y0) > 24)
      .append('text').attr('x', 6).attr('y', 16)
      .attr('font-size', '11px').attr('fill', '#fff').attr('font-weight', '500')
      .text((d: any) => d.data.label);

    cells.filter((d: any) => (d.x1 - d.x0) > 50 && (d.y1 - d.y0) > 38)
      .append('text').attr('x', 6).attr('y', 30)
      .attr('font-size', '10px').attr('fill', 'rgba(255,255,255,0.8)')
      .text((d: any) => FMT.format(d.data.value));
  }
}