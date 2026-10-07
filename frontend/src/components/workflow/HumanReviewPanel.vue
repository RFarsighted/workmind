<!-- frontend/src/components/workflow/HumanReviewPanel.vue -->
<!-- 人工审核面板：展示中间产物 + 填写修改意见 + 继续/放弃 -->
<template>
  <div class="review-panel">
    <div class="review-header">
      <span class="review-icon">👤</span>
      <div>
        <div class="review-title">等待人工审核</div>
        <div class="review-desc">请确认上方的分析结果，如需调整可以填写修改意见</div>
      </div>
    </div>

    <!-- 中间产物：展示各步骤的分析结果 -->
    <div v-if="intermediates.length" class="intermediates">
      <div
        v-for="item in intermediates"
        :key="item.key"
        class="intermediate-item"
      >
        <div class="item-label">{{ item.label }}</div>
        <div class="item-value">{{ item.value }}</div>
      </div>
    </div>

    <!-- 修改意见输入 -->
    <div class="feedback-area">
      <label class="feedback-label">修改意见（可选）</label>
      <textarea
        v-model="feedback"
        class="input"
        placeholder="如有问题，在此填写修改要求，AI 会根据你的意见重新生成。留空则直接使用当前结果继续。"
        rows="3"
      />
    </div>

    <!-- 操作按钮 -->
    <div class="review-actions">
      <button class="btn btn-ghost" @click="emit('abort')">
        取消
      </button>
      <button
        class="btn btn-primary"
        @click="emit('approve', feedback)"
        :disabled="wfStore.running"
      >
        {{ wfStore.running ? '执行中...' : (feedback.trim() ? '📝 采纳意见并继续' : '✅ 确认并继续') }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useWorkflowStore } from '@/stores/workflow.js'

const emit = defineEmits(['approve', 'abort'])

const wfStore = useWorkflowStore()
const feedback = ref('')

const intermediates = computed(() => wfStore.intermediates)
</script>

<style scoped>
.review-panel {
  background: var(--color-warning-bg);
  border: 1.5px solid var(--color-warning-border);
  border-radius: var(--radius-xl);
  padding: var(--space-lg);
  display: flex;
  flex-direction: column;
  gap: var(--space-md);
}

.review-header {
  display: flex;
  align-items: flex-start;
  gap: var(--space-md);
}

.review-icon { font-size: 24px; }

.review-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--color-warning-text);
  margin-bottom: 3px;
}

.review-desc {
  font-size: 12px;
  color: var(--color-warning-text);
  line-height: 1.5;
}

/* 中间产物展示 */
.intermediates {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: var(--space-md);
  background: color-mix(in srgb, var(--color-surface) 70%, transparent);
  border: 1px solid var(--color-warning-border);
  border-radius: var(--radius-lg);
}

.intermediate-item {}

.item-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: .06em;
  color: var(--color-warning-text);
  margin-bottom: 5px;
}

.item-value {
  font-size: 12px;
  color: var(--color-text);
  line-height: 1.65;
  white-space: pre-wrap;
  background: var(--color-surface);
  padding: 8px 10px;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-warning-border);
  max-height: 120px;
  overflow-y: auto;
}

/* 反馈输入 */
.feedback-label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  color: var(--color-warning-text);
  margin-bottom: 6px;
}

.input {
  background: var(--color-surface);
  border-color: var(--color-warning-border);
}

.input:focus { border-color: var(--color-warning); }

/* 操作按钮 */
.review-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-sm);
}
</style>
