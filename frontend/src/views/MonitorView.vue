<!-- frontend/src/views/MonitorView.vue -->
<template>
  <div class="monitor-view">
    <div class="metrics-grid">
      <MetricCard label="今日模型请求" :value="s.overview?.apiCallsToday ?? 0" :sub="`失败 ${s.overview?.failedCallsToday ?? 0} 次`" color="blue" />
      <MetricCard label="输入 Token" :value="formatTokens(s.overview?.inputTokensToday)" :sub="unknownHint" color="purple" />
      <MetricCard label="输出 Token" :value="formatTokens(s.overview?.outputTokensToday)" sub="准确用量；缺失项单独标记" color="amber" />
      <MetricCard label="平均响应" :value="`${s.latency?.avg ?? 0}ms`" :sub="`P99: ${s.latency?.p99 ?? 0}ms`" color="green" />
    </div>

    <div class="budget-bar-wrap">
      <div class="budget-label">
        <span>今日预算使用</span>
        <span class="budget-pct" :class="{ warn: (s.overview?.budgetUsedPct??0) >= 80, danger: (s.overview?.budgetUsedPct??0) >= 100 }">{{ s.overview?.budgetUsedPct ?? 0 }}%</span>
        <button class="btn-text-xs" @click="showBE = !showBE">修改预算</button>
      </div>
      <div class="budget-bar">
        <div class="budget-fill" :style="{ width: Math.min(s.overview?.budgetUsedPct??0, 100) + '%' }" :class="{ warn: (s.overview?.budgetUsedPct??0) >= 80, danger: (s.overview?.budgetUsedPct??0) >= 100 }" />
      </div>
      <div v-if="s.overview?.unknownUsageToday" class="budget-note">
        预算进度按已知 Token 计算；另有 {{ s.overview.unknownUsageToday }} 次请求用量未知
      </div>
      <div v-if="showBE" class="budget-edit">
        <input type="number" v-model.number="monitorStore.newBudget" class="input budget-input" min="1" />
        <span class="budget-unit">Token / 日</span>
        <button class="btn btn-primary btn-xs" @click="updateBudget">保存</button>
        <button class="btn btn-ghost btn-xs" @click="showBE = false">取消</button>
      </div>
    </div>

    <div class="charts-row">
      <div class="chart-card">
        <div class="chart-title">近 7 日 Token 消耗</div>
        <div class="bar-chart">
          <div v-for="day in (s.last7Days||[])" :key="day.date" class="bar-col">
            <div class="bar-group">
              <div class="bar input-bar" :style="{ height: barH(day.inputT) + 'px' }" :title="`输入 ${formatTokens(day.inputT)}`" />
              <div class="bar output-bar" :style="{ height: barH(day.outputT) + 'px' }" :title="`输出 ${formatTokens(day.outputT)}`" />
            </div>
            <div class="bar-label">{{ day.label }}</div>
            <div v-if="day.unknownCalls" class="bar-cost">{{ day.unknownCalls }} 未知</div>
          </div>
        </div>
        <div class="chart-legend">
          <span class="legend-item input">输入</span>
          <span class="legend-item output">输出</span>
        </div>
      </div>

      <div class="chart-card">
        <div class="chart-title">今日调用分布</div>
        <div v-if="!(s.byFeature?.length)" class="chart-empty">暂无今日数据</div>
        <div v-else class="feature-list">
          <div v-for="f in s.byFeature" :key="f.feature" class="feature-row">
            <span class="feature-label">{{ f.label }}</span>
            <div class="feature-bar-wrap"><div class="feature-bar" :style="{ width: featureBarW(f.calls) + '%' }" /></div>
            <span class="feature-calls">{{ f.calls }} 次</span>
            <span class="feature-tokens">{{ formatTokens(f.inputT + f.outputT) }} T</span>
          </div>
        </div>
      </div>

      <div class="chart-card">
        <div class="chart-title">响应时间</div>
        <div class="latency-stats">
          <div class="lat-item" v-for="(val, key) in latencyItems" :key="key">
            <div class="lat-label">{{ key }}</div>
            <div class="lat-value">{{ val }}ms</div>
          </div>
        </div>
      </div>
    </div>

    <div class="table-card">
      <div class="table-header">
        <span class="table-title">最近调用记录</span>
        <div class="table-filters">
          <select v-model="featureFilter" class="input filter-select">
            <option value="">全部功能</option>
            <option v-for="f in featureOptions" :key="f.feature" :value="f.feature">{{ f.label }}</option>
          </select>
          <button class="btn btn-ghost btn-sm" @click="loadStats">刷新</button>
        </div>
      </div>
      <div class="table-wrap">
        <table class="call-table">
          <thead><tr><th>时间</th><th>状态</th><th>功能</th><th>模型</th><th>输入 Token</th><th>输出 Token</th><th>延迟</th></tr></thead>
          <tbody>
            <tr v-if="!filteredCalls.length"><td colspan="7" class="empty-row">暂无记录，进行操作后刷新</td></tr>
            <tr v-for="(c,i) in filteredCalls" :key="i">
              <td class="time-cell">{{ fmtTime(c.time) }}</td>
              <td><span :class="c.success ? 'success-badge' : 'failure-badge'">{{ c.success ? '成功' : '失败' }}</span></td>
              <td><span class="feature-tag">{{ featureLabel(c.feature) }}</span></td>
              <td>{{ c.model || '未知' }}</td>
              <td>{{ c.inputT == null ? '未知' : formatTokens(c.inputT) }}</td>
              <td>{{ c.outputT == null ? '未知' : formatTokens(c.outputT) }}</td>
              <td>{{ c.latencyMs }}ms</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</template>
<script setup>
import { computed, h, ref } from 'vue'
import { useMonitorStore } from '@/stores/monitor.js'
const monitorStore = useMonitorStore()
const s = computed(() => monitorStore.stats)
const MetricCard = {
  props: ['label', 'value', 'sub', 'color'],
  setup(props) {
    return () => h('div', { class: ['metric-card', `color-${props.color}`] }, [
      h('div', { class: 'metric-value' }, props.value),
      h('div', { class: 'metric-label' }, props.label),
      h('div', { class: 'metric-sub' }, props.sub),
    ])
  },
}
const showBE = ref(false)
const featureFilter = ref('')
const featureNames = { chat:'对话助手', knowledge:'RAG 知识库', knowledge_embedding:'知识库向量化', agent:'任务 Agent', workflow:'内容工作流', erp:'ERP 审批', prompt:'Prompt 调试', prompt_ab:'A/B 回答', prompt_eval:'A/B 评分' }
const featureLabel = (f) => featureNames[f] || f
const unknownHint = computed(() => s.value.overview?.unknownUsageToday ? `${s.value.overview.unknownUsageToday} 次请求 Token 未知` : '已知 Token 用量')
function formatTokens(value) { return Number(value || 0).toLocaleString('zh-CN') }
async function updateBudget() {
  await monitorStore.updateBudget(); showBE.value = false
}
const maxT = computed(() => Math.max(...(s.value.last7Days||[]).map(d=>d.inputT+d.outputT), 1))
const maxC = computed(() => Math.max(...(s.value.byFeature||[]).map(f=>f.calls), 1))
function barH(val) { return val ? Math.max(2, Math.round((val/maxT.value)*80)) : 0 }
function featureBarW(calls) { return Math.round((calls/maxC.value)*100) }
const latencyItems = computed(() => ({ P50: s.value.latency?.p50??0, P90: s.value.latency?.p90??0, P99: s.value.latency?.p99??0, AVG: s.value.latency?.avg??0 }))
const filteredCalls = computed(() => { const c = s.value.recentCalls||[]; return featureFilter.value ? c.filter(x=>x.feature===featureFilter.value) : c })
const featureOptions = computed(() => [...new Set((s.value.recentCalls||[]).map(c=>c.feature))].map(f=>({ feature:f, label:featureLabel(f) })))
function fmtTime(iso) { if (!iso) return ''; const d = new Date(iso); return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}` }
</script>
<style scoped>
.monitor-view { height:100%; overflow-y:auto; padding:var(--space-lg) var(--space-xl); display:flex; flex-direction:column; gap:var(--space-lg); background:var(--color-bg); }
.metrics-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:var(--space-md); }
.metric-card { background:var(--color-surface); border:1px solid var(--color-border); border-radius:var(--radius-lg); padding:var(--space-md) var(--space-lg); }
.color-blue   { border-top:3px solid var(--color-info); }
.color-purple { border-top:3px solid var(--color-primary); }
.color-amber  { border-top:3px solid var(--color-warning); }
.color-green  { border-top:3px solid var(--color-success); }
.metric-value { font-size:24px; font-weight:800; color:var(--color-text); line-height:1.2; }
.metric-label { font-size:11px; font-weight:600; text-transform:uppercase; letter-spacing:.06em; color:var(--color-text-muted); margin-top:4px; }
.metric-sub { font-size:11px; color:var(--color-text-muted); margin-top:2px; }
.budget-bar-wrap { background:var(--color-surface); border:1px solid var(--color-border); border-radius:var(--radius-lg); padding:var(--space-md) var(--space-lg); }
.budget-label { display:flex; align-items:center; gap:8px; font-size:12px; color:var(--color-text-sub); margin-bottom:8px; }
.budget-pct { font-weight:700; color:var(--color-text); }
.budget-pct.warn { color:var(--color-warning); }
.budget-pct.danger { color:var(--color-danger); }
.btn-text-xs { font-size:11px; color:var(--color-primary); background:none; border:none; cursor:pointer; margin-left:auto; }
.budget-bar { height:6px; background:var(--color-border); border-radius:var(--radius-full); overflow:hidden; }
.budget-note { margin-top:6px; font-size:10px; color:var(--color-text-muted); }
.budget-fill { height:100%; background:var(--color-primary); border-radius:var(--radius-full); transition:width .5s; }
.budget-fill.warn { background:var(--color-warning); }
.budget-fill.danger { background:var(--color-danger); }
.budget-edit { display:flex; align-items:center; gap:8px; margin-top:10px; }
.budget-input { width:100px; padding:5px 8px; }
.budget-unit { font-size:11px; color:var(--color-text-muted); }
.btn-xs { padding:4px 10px; font-size:11px; }
.charts-row { display:grid; grid-template-columns:2fr 1.5fr 1fr; gap:var(--space-md); }
.chart-card { background:var(--color-surface); border:1px solid var(--color-border); border-radius:var(--radius-lg); padding:var(--space-lg); }
.chart-title { font-size:12px; font-weight:600; color:var(--color-text); margin-bottom:var(--space-md); }
.chart-empty { font-size:12px; color:var(--color-text-muted); text-align:center; padding:24px 0; }
.bar-chart { display:flex; align-items:flex-end; gap:var(--space-sm); height:100px; padding-bottom:4px; }
.bar-col { display:flex; flex-direction:column; align-items:center; flex:1; gap:3px; }
.bar-group { display:flex; align-items:flex-end; gap:2px; }
.bar { width:10px; border-radius:2px 2px 0 0; transition:height .3s; }
.input-bar { background:var(--color-primary); }
.output-bar { background:var(--color-info); }
.bar-label { font-size:9px; color:var(--color-text-muted); }
.bar-cost { font-size:9px; color:var(--color-text-muted); }
.chart-legend { display:flex; gap:var(--space-md); margin-top:var(--space-sm); }
.legend-item { display:flex; align-items:center; gap:4px; font-size:10px; color:var(--color-text-muted); }
.legend-item::before { content:''; width:10px; height:3px; border-radius:2px; display:inline-block; }
.legend-item.input::before { background:var(--color-primary); }
.legend-item.output::before { background:var(--color-info); }
.feature-list { display:flex; flex-direction:column; gap:8px; }
.feature-row { display:flex; align-items:center; gap:8px; }
.feature-label { font-size:11px; color:var(--color-text-sub); width:70px; flex-shrink:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.feature-bar-wrap { flex:1; height:6px; background:var(--color-border); border-radius:var(--radius-full); overflow:hidden; }
.feature-bar { height:100%; background:var(--color-primary); border-radius:var(--radius-full); transition:width .4s; }
.feature-calls { font-size:11px; color:var(--color-text-muted); width:28px; text-align:right; }
.feature-tokens { font-size:10px; color:var(--color-text-muted); width:58px; text-align:right; }
.latency-stats { display:grid; grid-template-columns:1fr 1fr; gap:var(--space-sm); }
.lat-item { text-align:center; padding:10px 6px; background:var(--color-bg); border-radius:var(--radius-md); border:1px solid var(--color-border-light); }
.lat-label { font-size:10px; font-weight:700; text-transform:uppercase; letter-spacing:.06em; color:var(--color-text-muted); }
.lat-value { font-size:18px; font-weight:800; color:var(--color-text); margin:4px 0; }
.table-card { background:var(--color-surface); border:1px solid var(--color-border); border-radius:var(--radius-lg); overflow:hidden; }
.table-header { display:flex; align-items:center; justify-content:space-between; padding:var(--space-md) var(--space-lg); border-bottom:1px solid var(--color-border-light); }
.table-title { font-size:13px; font-weight:600; color:var(--color-text); }
.table-filters { display:flex; gap:var(--space-sm); }
.filter-select { padding:5px 10px; font-size:12px; }
.btn-sm { padding:5px 12px; font-size:12px; }
.table-wrap { overflow-x:auto; }
.call-table { width:100%; border-collapse:collapse; font-size:12px; }
.call-table th { padding:8px 16px; background:var(--color-bg); font-size:10px; font-weight:600; text-transform:uppercase; letter-spacing:.06em; color:var(--color-text-muted); text-align:left; border-bottom:1px solid var(--color-border); }
.call-table td { padding:8px 16px; border-bottom:1px solid var(--color-border-light); color:var(--color-text-sub); }
.call-table tr.from-cache td { opacity:.7; }
.call-table tr:hover td { background:var(--color-border-light); }
.empty-row { text-align:center; color:var(--color-text-muted); padding:24px !important; }
.time-cell { font-family:var(--font-mono); color:var(--color-text-muted); }
.feature-tag { font-size:10px; padding:2px 7px; background:var(--color-primary-bg); color:var(--color-primary); border-radius:var(--radius-full); }
.cache-badge { font-size:10px; padding:2px 7px; background:var(--color-primary-bg); color:var(--color-primary); border-radius:var(--radius-full); }
.api-badge { font-size:10px; padding:2px 7px; background:var(--color-border-light); color:var(--color-text-muted); border-radius:var(--radius-full); }
.success-badge { font-size:10px; padding:2px 7px; background:var(--color-success-bg); color:var(--color-success-text); border-radius:var(--radius-full); }
.failure-badge { font-size:10px; padding:2px 7px; background:var(--color-danger-bg); color:var(--color-danger-text); border-radius:var(--radius-full); }

@media (max-width: 1100px) {
  .metrics-grid { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .charts-row { grid-template-columns:minmax(0,1.4fr) minmax(0,1fr); }
  .charts-row .chart-card:last-child { grid-column:1 / -1; }
}

@media (max-width: 680px) {
  .monitor-view { padding:14px; gap:14px; }
  .metrics-grid, .charts-row { grid-template-columns:minmax(0,1fr); }
  .charts-row .chart-card:last-child { grid-column:auto; }
  .metric-card, .chart-card { padding:14px; }
  .table-header { align-items:flex-start; flex-direction:column; gap:10px; padding:14px; }
  .table-filters { width:100%; }
  .filter-select { min-width:0; flex:1; }
  .budget-bar-wrap { padding:14px; }
  .budget-edit { flex-wrap:wrap; }
}
</style>
