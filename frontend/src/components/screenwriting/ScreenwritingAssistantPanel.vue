<template>
  <aside class="ai-chat-panel">
    <section class="assistant-shell">
      <ScreenwritingAssistantHeader
        :connected-model-id="connectedModelId"
        :message-count="messages.length"
      />

      <ScreenwritingAssistantThread
        ref="threadRef"
        :messages="messages"
        :streaming-message-id="streamingMessageId"
      />

      <ScreenwritingAssistantComposer
        ref="composerRef"
        :model-value="modelValue"
        :is-sending="isSending"
        :input-limit="inputLimit"
        @update:model-value="emit('update:modelValue', $event)"
        @send="emit('send')"
        @new-conversation="emit('new-conversation')"
        @insert-stage-prompt="emit('insert-stage-prompt')"
        @quote-events="emit('quote-events')"
        @clear-composer="emit('clear-composer')"
      />
    </section>
  </aside>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import ScreenwritingAssistantComposer from './ScreenwritingAssistantComposer.vue'
import ScreenwritingAssistantHeader from './ScreenwritingAssistantHeader.vue'
import ScreenwritingAssistantThread from './ScreenwritingAssistantThread.vue'
import type { ChatMessage } from './types'

interface AssistantThreadExpose {
  followOutput: () => Promise<void>
  resetAutoScroll: () => void
  scrollToBottom: (behavior?: ScrollBehavior) => void
}

interface AssistantComposerExpose {
  focusComposer: () => void
}

withDefaults(defineProps<{
  modelValue: string
  messages: ChatMessage[]
  connectedModelId: string
  isSending: boolean
  streamingMessageId: number | null
  inputLimit?: number
}>(), {
  inputLimit: 2000,
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
  send: []
  'new-conversation': []
  'insert-stage-prompt': []
  'quote-events': []
  'clear-composer': []
}>()

const threadRef = ref<AssistantThreadExpose | null>(null)
const composerRef = ref<AssistantComposerExpose | null>(null)

const focusComposer = () => {
  composerRef.value?.focusComposer()
}

const followOutput = async () => {
  await threadRef.value?.followOutput()
}

const resetAutoScroll = () => {
  threadRef.value?.resetAutoScroll()
}

const scrollToBottom = (behavior?: ScrollBehavior) => {
  threadRef.value?.scrollToBottom(behavior)
}

defineExpose({
  focusComposer,
  followOutput,
  resetAutoScroll,
  scrollToBottom,
})
</script>

<style scoped>
.ai-chat-panel {
  min-height: 0;
  overflow: hidden;
}

.assistant-shell {
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 18px;
  background:
    radial-gradient(circle at 20% 0%, rgba(37, 99, 235, 0.14), transparent 34%),
    linear-gradient(180deg, rgba(15, 22, 32, 0.92), rgba(7, 11, 17, 0.96));
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.05),
    0 22px 52px rgba(0, 0, 0, 0.42);
  overflow: hidden;
}

@media (max-width: 920px) {
  .ai-chat-panel {
    overflow: visible;
  }

  .assistant-shell {
    min-height: 560px;
  }
}
</style>
