import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import http from '@/utils/http.js'
import { useAppStore } from './app.js'

export const useMonitorStore = defineStore('monitor', () => {
  const appStore = useAppStore()
  const stats = ref({
    overview: { apiCallsToday: 0, inputTokensToday: 0, outputTokensToday: 0,
      unknownUsageToday: 0, dailyBudgetTokens: 1_000_000, budgetUsedPct: 0 },
    last7Days: [], byFeature: [], latency: { avg: 0, p50: 0, p90: 0, p99: 0 }, recentCalls: [],
  })
  const newBudget = ref(1_000_000)
  const loading = ref(false)
  let pollTimer = null
  let budgetWarningShown = false

  const budgetWarning = computed(() => {
    const overview = stats.value.overview || {}
    const pct = overview.budgetUsedPct || 0
    if (pct < 80) {
      budgetWarningShown = false
      return null
    }
    if (!budgetWarningShown) {
      budgetWarningShown = true
      return `${overview.inputTokensToday + overview.outputTokensToday} / ${overview.dailyBudgetTokens} Token (${pct}%)`
    }
    return null
  })

  async function loadStats() {
    loading.value = true
    try {
      const data = await http.get('/monitor/stats')
      stats.value = data
      newBudget.value = data.overview?.dailyBudgetTokens ?? 1_000_000
    } catch {
      // Keep the last successful snapshot visible during temporary network errors.
    } finally {
      loading.value = false
    }
  }

  async function updateBudget(value = newBudget.value) {
    await http.put('/monitor/budget', { dailyBudgetTokens: value })
    await loadStats()
    appStore.toast.success('每日 Token 预算已更新')
  }

  function startPolling() {
    if (pollTimer) return
    loadStats()
    pollTimer = setInterval(loadStats, 10000)
  }

  function stopPolling() {
    if (pollTimer) clearInterval(pollTimer)
    pollTimer = null
  }

  return { stats, newBudget, loading, budgetWarning, loadStats, updateBudget, startPolling, stopPolling }
})
