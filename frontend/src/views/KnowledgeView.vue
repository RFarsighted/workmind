<!-- frontend/src/views/KnowledgeView.vue -->
<template>
  <div class="knowledge-view">
    <aside class="doc-panel">
      <DocumentUploader />
      <div class="divider" />
      <DocumentList />
    </aside>
    <RagChat />
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useKnowledgeStore } from '@/stores/knowledge.js'
import DocumentUploader from '@/components/rag/DocumentUploader.vue'
import DocumentList from '@/components/rag/DocumentList.vue'
import RagChat from '@/components/rag/RagChat.vue'

const knStore = useKnowledgeStore()
onMounted(() => { knStore.loadDocuments(); knStore.loadCategories() })
</script>

<style scoped>
.knowledge-view { display:flex; height:100%; overflow:hidden; background:var(--color-bg); }
.doc-panel { width:300px; flex-shrink:0; background:var(--color-surface); border-right:1px solid var(--color-border); display:flex; flex-direction:column; overflow:hidden; }
.divider { height:1px; background:var(--color-border); flex-shrink:0; }

@media (max-width: 940px) {
  .doc-panel { width:260px; }
}

@media (max-width: 700px) {
  .knowledge-view { flex-direction:column; }
  .doc-panel { width:100%; height:42%; min-height:210px; flex:0 1 42%; border-right:0; border-bottom:1px solid var(--color-border); }
  .rag-chat { min-height:0; }
}
</style>
