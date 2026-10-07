// frontend/src/stores/agent.js
// Agent 模块状态：任务历史、工具调用步骤、执行状态
import { defineStore } from 'pinia'
import { ref } from 'vue'
import { fetchStream } from '@/utils/http.js'
import http from '@/utils/http.js'
import { useAppStore } from './app.js'

export const useAgentStore = defineStore('agent', () => {
  const appStore = useAppStore()

  // ── 工具列表（从后端加载，默认值保证始终可见）──────────────
  const toolList = ref([
    { name: 'read_doc',     label: '文档检索', description: '从公司知识库检索文档' },
    { name: 'calculate',    label: '数学计算', description: '金额、工期等数学计算' },
    { name: 'get_date',     label: '日期查询', description: '日期查询和工作日计算' },
    { name: 'write_report', label: '生成报告', description: '生成并保存分析报告' },
    { name: 'send_notify',  label: '模拟通知', description: '生成模拟发送结果，不会联系外部人员' },
  ])
  const examples = ref([
    { title: '金额计算', task: '计算 1500 + 800 的总和，并用一句话说明结果。' },
    { title: '知识库查询', task: '从公司知识库查询差旅报销标准，并总结最重要的两点。' },
    { title: '日期计算', task: '今天是几号？从今天起 30 天后是什么日期？' },
    { title: '生成报告', task: '根据你掌握的信息生成一份简短的 WorkMind 模块介绍报告并保存。' },
    { title: '年假查询', task: '从知识库查询公司的年假政策，计算今年还剩多少年假（假设已用6天、总共15天），并生成一条给 HR 的模拟通知。' },
  ])

  async function loadMeta() {
    try {
      const [toolsRes, examplesRes] = await Promise.all([
        http.get('/agent/tools'),
        http.get('/agent/examples'),
      ])
      if (toolsRes.tools?.length)     toolList.value = toolsRes.tools
      if (examplesRes.examples?.length) examples.value = examplesRes.examples
    } catch {}
  }

  // ── 任务执行历史 ───────────────────────────────────────────
  // 每个任务是一条记录：{ id, task, steps, answer, status, startTime, duration }
  const tasks    = ref([])
  const running  = ref(false)

  // 当前正在执行的任务状态（实时更新）
  const currentTask = ref(null)

  let taskId = 0

  // ── 执行任务 ───────────────────────────────────────────────
  async function runTask(taskText) {
    if (!taskText.trim() || running.value) return

    running.value = true
    const id = ++taskId
    const startTime = Date.now()

    // 创建任务记录（先加进列表，实时更新）
    const task = {
      id,
      task:      taskText,
      steps:     [],       // 工具调用步骤数组
      answer:    '',       // 最终回答
      status:    'running',  // running | done | error
      startTime: new Date().toISOString(),
      duration:  0,
    }

    tasks.value.unshift(task)
    currentTask.value = task

    await fetchStream(
      '/api/agent/run',
      { task: taskText },
      {
        onToken: (token) => {
          task.answer += token
        },

        onEvent: (event, data) => {
          if (event === 'start') {
            task.status = 'running'
          }

          // 工具被调用：记录步骤
          if (event === 'tool_call') {
            task.steps.push({
              id:       task.steps.length + 1,
              callId:   data.callId,
              toolName: data.toolName,
              label:    data.label,
              args:     data.args,
              result:   null,
              status:   'running',   // running | done
              startMs:  Date.now(),
            })
          }

          // 工具执行完毕：更新最后一个 running 步骤
          if (event === 'tool_result') {
            const step = task.steps.find(s => s.callId === data.callId)
            if (step) {
              step.result    = data.resultText
              step.status    = data.status || 'done'
              step.durationMs = Date.now() - step.startMs
            }
          }

          if (event === 'done') {
            task.status   = 'done'
            task.duration = Date.now() - startTime
            currentTask.value = null
          }

          if (event === 'error') {
            task.status = 'error'
            task.answer = task.answer || data.message || '任务执行失败'
            task.steps.forEach(step => {
              if (step.status === 'running') step.status = 'error'
            })
            currentTask.value = null
            appStore.toast.error(data.message || '执行出错')
          }
        },

        onDone: () => {
          task.status   = 'done'
          task.duration = Date.now() - startTime
          currentTask.value = null
        },

        onError: (err) => {
          task.status = 'error'
          task.answer = task.answer || '网络错误，请重试'
          task.steps.forEach(step => {
            if (step.status === 'running') step.status = 'error'
          })
          currentTask.value = null
          appStore.toast.error(err.message)
        },
      }
    )

    running.value = false
  }

  function clearTasks() {
    tasks.value = []
    currentTask.value = null
  }

  return {
    toolList, examples,
    tasks, running, currentTask,
    loadMeta, runTask, clearTasks,
  }
})
