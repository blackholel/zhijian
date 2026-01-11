<template>
  <div class="chat-container" ref="chatContainerRef">
    <ChatSidebarComponent
      :current-chat-id="currentChatId"
      :chats-list="chatsList"
      :is-sidebar-open="chatUIStore.isSidebarOpen"
      :is-initial-render="localUIState.isInitialRender"
      :single-mode="props.singleMode"
      :agents="agents"
      :selected-agent-id="currentAgentId"
      :is-creating-new-chat="chatUIStore.creatingNewChat"
      :show-agent-list="props.showAgentList"
      :builtin-agents="props.builtinAgents"
      :my-agents="props.myAgents"
      :public-agents="props.publicAgents"
      @create-chat="createNewChat"
      @select-chat="selectChat"
      @delete-chat="deleteChat"
      @rename-chat="renameChat"
      @toggle-sidebar="toggleSidebar"
      @open-agent-modal="openAgentModal"
      @select-agent="(id) => emit('select-agent', id)"
      @create-agent="() => emit('create-agent')"
      @edit-agent="(id) => emit('edit-agent', id)"
      @delete-agent="(id) => emit('delete-agent', id)"
      @duplicate-agent="(id) => emit('duplicate-agent', id)"
      :class="{
        'floating-sidebar': isSmallContainer,
        'sidebar-open': chatUIStore.isSidebarOpen,
        'no-transition': localUIState.isInitialRender,
        'collapsed': isSmallContainer && !chatUIStore.isSidebarOpen
      }"
    />
    <div class="sidebar-backdrop" v-if="chatUIStore.isSidebarOpen && isSmallContainer" @click="toggleSidebar"></div>
    <div class="chat">
      <div class="chat-header">
        <div class="header__left">
          <slot name="header-left" class="nav-btn"></slot>
          <div type="button" class="agent-nav-btn" v-if="!chatUIStore.isSidebarOpen" @click="toggleSidebar">
            <PanelLeftOpen  class="nav-btn-icon" size="18"/>
          </div>
                    <div
            type="button"
            class="agent-nav-btn"
            v-if="!chatUIStore.isSidebarOpen"
            :class="{ 'is-disabled': chatUIStore.creatingNewChat }"
            @click="createNewChat"
          >
            <LoaderCircle v-if="chatUIStore.creatingNewChat" class="nav-btn-icon loading-icon" size="18"/>
            <MessageCirclePlus v-else class="nav-btn-icon"  size="18"/>
            <span class="text" :class="{'hide-text': isMediumContainer}">新对话</span>
          </div>
          <div
            v-if="!props.singleMode"
            class="agent-nav-btn"
            @click="openAgentModal"
          >
            <span class="text">{{ currentAgentName || '选择智能体' }}</span>
            <ChevronDown size="16" class="switch-icon" />
          </div>

        </div>
        <div class="header__right">
          <!-- AgentState 显示按钮 - 只在智能体支持 todo 或 files 能力时显示 -->
          <AgentPopover
            v-if="hasAgentStateContent"
            v-model:visible="agentStatePopoverVisible"
            :agent-state="currentAgentState"
            @refresh="handleAgentStateRefresh"
          >
            <div
              class="agent-nav-btn agent-state-btn"
              :class="{ 'has-content': hasAgentStateContent }"
              :title="hasAgentStateContent ? '查看工作状态' : '暂无工作状态'"
            >
              <FolderDotIcon class="nav-btn-icon" size="18"/>
              <span v-if="hasAgentStateContent" class="text">状态</span>
            </div>
          </AgentPopover>
          <slot name="header-right" :is-medium-container="isMediumContainer"></slot>
        </div>
      </div>

      <!-- 加载状态：加载消息 -->
      <div v-if="isLoadingMessages" class="chat-loading">
        <div class="loading-spinner"></div>
        <span>正在加载消息...</span>
      </div>

      <div v-else-if="!conversations.length" class="chat-examples">
        <div style="margin-bottom: 150px"></div>
        <h1>您好，我是{{ currentAgentName }}！</h1>
      </div>
      <div class="chat-box" ref="messagesContainer">
        <div class="conv-box" v-for="(conv, index) in conversations" :key="index">
          <AgentMessageComponent
            v-for="(message, msgIndex) in conv.messages"
            :message="message"
            :key="msgIndex"
            :is-processing="isProcessing && conv.status === 'streaming' && msgIndex === conv.messages.length - 1"
            :show-refs="showMsgRefs(message)"
            @retry="retryMessage(message)"
          >
          </AgentMessageComponent>
          <!-- 显示对话最后一个消息使用的模型 -->
          <RefsComponent
            v-if="shouldShowRefs(conv)"
            :message="getLastMessage(conv)"
            :show-refs="['model', 'copy']"
            :is-latest-message="false"
          />
        </div>

        <!-- 生成中的加载状态 - 增强条件支持主聊天和resume流程 -->
        <div class="generating-status" v-if="isProcessing && conversations.length > 0">
          <div class="generating-indicator">
            <div class="loading-dots">
              <div></div>
              <div></div>
              <div></div>
            </div>
            <span class="generating-text">正在生成回复...</span>
          </div>
        </div>
      </div>
      <div class="bottom" :class="{ 'start-screen': !conversations.length }">
        <!-- 人工审批弹窗 - 放在输入框上方 -->
        <HumanApprovalModal
          :visible="approvalState.showModal"
          :question="approvalState.question"
          :operation="approvalState.operation"
          @approve="handleApprove"
          @reject="handleReject"
        />

        <div class="message-input-wrapper">
          <AgentInputArea
            ref="messageInputRef"
            v-model="userInput"
            :is-loading="isProcessing"
            :disabled="!currentAgent"
            :send-button-disabled="(!userInput || !currentAgent) && !isProcessing"
            placeholder="输入问题..."
            :supports-file-upload="supportsFileUpload"
            :agent-id="currentAgentId"
            :thread-id="currentChatId"
            :ensure-thread="ensureActiveThread"
            @send="handleSendOrStop"
          />

          <!-- 示例问题 -->
          <div class="example-questions" v-if="!conversations.length && exampleQuestions.length > 0">
            <div class="example-chips">
              <div
                v-for="question in exampleQuestions"
                :key="question.id"
                class="example-chip"
                @click="handleExampleClick(question.text)"
              >
                {{ question.text }}
              </div>
            </div>
          </div>

          <div class="bottom-actions" v-else>
            <p class="note">请注意辨别内容的可靠性</p>
          </div>
        </div>
      </div>
    </div>

    </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch, nextTick, computed, onUnmounted } from 'vue';
import { message } from 'ant-design-vue';
import AgentInputArea from '@/components/AgentInputArea.vue'
import AgentMessageComponent from '@/components/AgentMessageComponent.vue'
import ChatSidebarComponent from '@/components/ChatSidebarComponent.vue'
import RefsComponent from '@/components/RefsComponent.vue'
import { PanelLeftOpen, MessageCirclePlus, LoaderCircle, FolderDotIcon, ChevronDown } from 'lucide-vue-next';
import { handleChatError, handleValidationError } from '@/utils/errorHandler';
import { ScrollController } from '@/utils/scrollController';
import { AgentValidator } from '@/utils/agentValidator';
import { useAgentStore } from '@/stores/agent';
import { useChatUIStore } from '@/stores/chatUI';
import { storeToRefs } from 'pinia';
import { MessageProcessor } from '@/utils/messageProcessor';
import { agentApi, threadApi } from '@/apis';
import HumanApprovalModal from '@/components/HumanApprovalModal.vue';
import { useApproval } from '@/composables/useApproval';
import { useAgentStreamHandler } from '@/composables/useAgentStreamHandler';
import AgentPopover from '@/components/AgentPopover.vue';

// ==================== PROPS & EMITS ====================
const props = defineProps({
  agentId: { type: String, default: '' },
  singleMode: { type: Boolean, default: true },
  showAgentList: { type: Boolean, default: false },
  builtinAgents: { type: Array, default: () => [] },
  myAgents: { type: Array, default: () => [] },
  publicAgents: { type: Array, default: () => [] }
});
const emit = defineEmits([
  'open-config',
  'open-agent-modal',
  'select-agent',
  'create-agent',
  'edit-agent',
  'delete-agent',
  'duplicate-agent'
]);

// ==================== STORE MANAGEMENT ====================
const agentStore = useAgentStore();
const chatUIStore = useChatUIStore();
const {
  agents,
  selectedAgentId,
  defaultAgentId,
} = storeToRefs(agentStore);

// ==================== LOCAL CHAT & UI STATE ====================
const userInput = ref('');

// 从智能体元数据获取示例问题
const exampleQuestions = computed(() => {
  const agentId = currentAgentId.value;
  let examples = [];
  if (agentId && agents.value && agents.value.length > 0) {
    const agent = agents.value.find(a => a.agent_id === agentId || a.id === agentId);
    examples = agent ? (agent.examples || []) : [];
  }
  return examples.map((text, index) => ({
    id: index + 1,
    text: text
  }));
});

// Keep per-thread streaming scratch data in a consistent shape.
const createOnGoingConvState = () => ({
  msgChunks: {},
  currentRequestKey: null,
  currentAssistantKey: null,
  toolCallBuffers: {}
});

// 业务状态（保留在组件本地）
const chatState = reactive({
  currentThreadId: null,
  // 以threadId为键的线程状态
  threadStates: {}
});

// 组件级别的线程和消息状态
const threads = ref([]);
const threadMessages = ref({});

// 本地 UI 状态（仅在本组件使用）
const localUIState = reactive({
  isInitialRender: true,
  containerWidth: 0,
});

// AgentState Popover 状态
const agentStatePopoverVisible = ref(false);

// ==================== COMPUTED PROPERTIES ====================
const currentAgentId = computed(() => {
  if (props.singleMode) {
    return props.agentId || defaultAgentId.value;
  } else {
    return selectedAgentId.value;
  }
});

const currentAgentName = computed(() => {
  const agentId = currentAgentId.value;
  if (agentId && agents.value && agents.value.length > 0) {
    const agent = agents.value.find(a => a.agent_id === agentId || a.id === agentId);
    return agent ? agent.name : '智能体';
  }
  return '智能体加载中……';
});

const currentAgent = computed(() => {
  if (!currentAgentId.value || !agents.value || !agents.value.length) return null;
  return agents.value.find(a => a.agent_id === currentAgentId.value || a.id === currentAgentId.value) || null;
});
const chatsList = computed(() => threads.value || []);
const currentChatId = computed(() => chatState.currentThreadId);
const currentThread = computed(() => {
  if (!currentChatId.value) return null;
  return threads.value.find(thread => thread.id === currentChatId.value) || null;
});

// 检查当前智能体是否支持文件上传
const supportsFileUpload = computed(() => {
  if (!currentAgent.value) return false;
  const capabilities = currentAgent.value.capabilities || [];
  return capabilities.includes('file_upload');
});
const supportsTodo = computed(() => {
  if (!currentAgent.value) return false;
  const capabilities = currentAgent.value.capabilities || [];
  return capabilities.includes('todo');
});

const supportsFiles = computed(() => {
  if (!currentAgent.value) return false;
  const capabilities = currentAgent.value.capabilities || [];
  return capabilities.includes('files');
});

// AgentState 相关计算属性
const currentAgentState = computed(() => {
  return currentChatId.value ? getThreadState(currentChatId.value)?.agentState || null : null;
});

const countFiles = (files) => {
  if (!Array.isArray(files)) return 0;
  let c = 0;
  for (const item of files) {
    if (item && typeof item === 'object') c += Object.keys(item).length;
  }
  return c;
};

const hasAgentStateContent = computed(() => {
  const s = currentAgentState.value;
  if (!s) return false;
  const todoCount = Array.isArray(s.todos) ? s.todos.length : 0;
  const fileCount = countFiles(s.files);
  return todoCount > 0 || fileCount > 0;
});

const currentThreadMessages = computed(() => threadMessages.value[currentChatId.value] || []);

// 计算是否显示Refs组件的条件
const shouldShowRefs = computed(() => {
  return (conv) => {
    return getLastMessage(conv) &&
           conv.status !== 'streaming' &&
           !approvalState.showModal &&
           !(approvalState.threadId &&
             chatState.currentThreadId === approvalState.threadId &&
             isProcessing.value);
  };
});

// 当前线程状态的computed属性
const currentThreadState = computed(() => {
  return getThreadState(currentChatId.value);
});

const onGoingConvMessages = computed(() => {
  const threadState = currentThreadState.value;
  if (!threadState || !threadState.onGoingConv) return [];

  const msgs = Object.values(threadState.onGoingConv.msgChunks).map(MessageProcessor.mergeMessageChunk);
  return msgs.length > 0
    ? MessageProcessor.convertToolResultToMessages(msgs).filter(msg => msg.type !== 'tool')
    : [];
});

const historyConversations = computed(() => {
  return MessageProcessor.convertServerHistoryToMessages(currentThreadMessages.value);
});

const conversations = computed(() => {
  const historyConvs = historyConversations.value;

  // 如果有进行中的消息且线程状态显示正在流式处理，添加进行中的对话
  if (onGoingConvMessages.value.length > 0) {
    const onGoingConv = {
      messages: onGoingConvMessages.value,
      status: 'streaming'
    };
    return [...historyConvs, onGoingConv];
  }
  return historyConvs;
});

const isLoadingMessages = computed(() => chatUIStore.isLoadingMessages);
const isStreaming = computed(() => {
  const threadState = currentThreadState.value;
  return threadState ? threadState.isStreaming : false;
});
const isProcessing = computed(() => isStreaming.value);
const isSmallContainer = computed(() => localUIState.containerWidth <= 520);
const isMediumContainer = computed(() => localUIState.containerWidth <= 768);

// ==================== SCROLL & RESIZE HANDLING ====================
const chatContainerRef = ref(null);
const scrollController = new ScrollController('.chat');
let resizeObserver = null;

onMounted(() => {
  nextTick(() => {
    if (chatContainerRef.value) {
      localUIState.containerWidth = chatContainerRef.value.offsetWidth;
      resizeObserver = new ResizeObserver(entries => {
        for (let entry of entries) {
          localUIState.containerWidth = entry.contentRect.width;
        }
      });
      resizeObserver.observe(chatContainerRef.value);
    }
    const chatContainer = document.querySelector('.chat');
    if (chatContainer) {
      chatContainer.addEventListener('scroll', scrollController.handleScroll, { passive: true });
    }
  });
  setTimeout(() => { localUIState.isInitialRender = false; }, 300);
});

onUnmounted(() => {
  if (resizeObserver) resizeObserver.disconnect();
  scrollController.cleanup();
    // 清理所有线程状态
  resetOnGoingConv();
});

// ==================== THREAD STATE MANAGEMENT ====================
// 获取指定线程的状态，如果不存在则创建
const getThreadState = (threadId) => {
  if (!threadId) return null;
  if (!chatState.threadStates[threadId]) {
    chatState.threadStates[threadId] = {
      isStreaming: false,
      streamAbortController: null,
      onGoingConv: createOnGoingConvState(),
      agentState: null  // 添加 agentState 字段
    };
  }
  return chatState.threadStates[threadId];
};

// 清理指定线程的状态
const cleanupThreadState = (threadId) => {
  if (!threadId) return;
  const threadState = chatState.threadStates[threadId];
  if (threadState) {
    if (threadState.streamAbortController) {
      threadState.streamAbortController.abort();
    }
    delete chatState.threadStates[threadId];
  }
};

// ==================== STREAM HANDLING LOGIC ====================
const resetOnGoingConv = (threadId = null) => {
  console.log(`🔄 [RESET] Resetting on going conversation: ${new Date().toLocaleTimeString()}.${new Date().getMilliseconds()}`, threadId);

  const targetThreadId = threadId || currentChatId.value;

  if (targetThreadId) {
    // 清理指定线程的状态
    const threadState = getThreadState(targetThreadId);
    if (threadState) {
      if (threadState.streamAbortController) {
        threadState.streamAbortController.abort();
        threadState.streamAbortController = null;
      }

      // 直接重置对话状态
      threadState.onGoingConv = createOnGoingConvState();
    }
  } else {
    // 如果没有当前线程，清理所有线程状态
    Object.keys(chatState.threadStates).forEach(tid => {
      cleanupThreadState(tid);
    });
  }
};

// ==================== 线程管理方法 ====================
// 获取当前智能体的线程列表
const fetchThreads = async (agentId = null) => {
  const targetAgentId = agentId || currentAgentId.value;
  if (!targetAgentId) return;

  chatUIStore.isLoadingThreads = true;
  try {
    const fetchedThreads = await threadApi.getThreads(targetAgentId);
    threads.value = fetchedThreads || [];
  } catch (error) {
    console.error('Failed to fetch threads:', error);
    handleChatError(error, 'fetch');
    throw error;
  } finally {
    chatUIStore.isLoadingThreads = false;
  }
};

// 创建新线程
const createThread = async (agentId, title = '新的对话') => {
  if (!agentId) return null;

  chatState.isCreatingThread = true;
  try {
    const thread = await threadApi.createThread(agentId, title);
    if (thread) {
      threads.value.unshift(thread);
      threadMessages.value[thread.id] = [];
    }
    return thread;
  } catch (error) {
    console.error('Failed to create thread:', error);
    handleChatError(error, 'create');
    throw error;
  } finally {
    chatState.isCreatingThread = false;
  }
};

// 删除线程
const deleteThread = async (threadId) => {
  if (!threadId) return;

  chatState.isDeletingThread = true;
  try {
    await threadApi.deleteThread(threadId);
    threads.value = threads.value.filter(thread => thread.id !== threadId);
    delete threadMessages.value[threadId];

    if (chatState.currentThreadId === threadId) {
      chatState.currentThreadId = null;
    }
  } catch (error) {
    console.error('Failed to delete thread:', error);
    handleChatError(error, 'delete');
    throw error;
  } finally {
    chatState.isDeletingThread = false;
  }
};

// 更新线程标题
const updateThread = async (threadId, title) => {
  if (!threadId || !title) return;

  chatState.isRenamingThread = true;
  try {
    await threadApi.updateThread(threadId, title);
    const thread = threads.value.find(t => t.id === threadId);
    if (thread) {
      thread.title = title;
    }
  } catch (error) {
    console.error('Failed to update thread:', error);
    handleChatError(error, 'update');
    throw error;
  } finally {
    chatState.isRenamingThread = false;
  }
};

// 获取线程消息
const fetchThreadMessages = async ({ agentId, threadId, delay = 0 }) => {
  if (!threadId || !agentId) return;

  // 如果指定了延迟，等待指定时间（用于确保后端数据库事务提交）
  if (delay > 0) {
    await new Promise(resolve => setTimeout(resolve, delay));
  }

  try {
    const response = await agentApi.getAgentHistory(agentId, threadId);
    console.log(`🔄 [FETCH] Thread messages: ${new Date().toLocaleTimeString()}.${new Date().getMilliseconds()}`, response);
    threadMessages.value[threadId] = response.history || [];
  } catch (error) {
    handleChatError(error, 'load');
    throw error;
  }
};

const fetchAgentState = async (agentId, threadId) => {
  if (!agentId || !threadId) return;
  try {
    const res = await agentApi.getAgentState(agentId, threadId);
    const ts = getThreadState(threadId);
    if (ts) ts.agentState = res.agent_state || null;
  } catch (error) {}
};

const ensureActiveThread = async (title = '新的对话') => {
  if (currentChatId.value) return currentChatId.value;
  try {
    const newThread = await createThread(currentAgentId.value, title || '新的对话');
    if (newThread) {
      chatState.currentThreadId = newThread.id;
      return newThread.id;
    }
  } catch (error) {
    // createThread 已处理错误提示
  }
  return null;
};

// ==================== 审批功能管理 ====================
const { approvalState, handleApproval, processApprovalInStream } = useApproval({
  getThreadState,
  resetOnGoingConv,
  fetchThreadMessages
});

const { handleAgentResponse } = useAgentStreamHandler({
  getThreadState,
  processApprovalInStream,
  currentAgentId,
  supportsTodo,
  supportsFiles
});

// 发送消息并处理流式响应
const sendMessage = async ({ agentId, threadId, text, signal = undefined, imageData = undefined }) => {
  if (!agentId || !threadId || !text) {
    const error = new Error("Missing agent, thread, or message text");
    handleChatError(error, 'send');
    return Promise.reject(error);
  }

  // 如果是新对话，用消息内容作为标题
  if ((threadMessages.value[threadId] || []).length === 0) {
    updateThread(threadId, text);
  }

  const requestData = {
    query: text,
    config: {
      thread_id: threadId,
    },
  };

  // 如果有图片，添加到请求中
  if (imageData && imageData.imageContent) {
    requestData.image_content = imageData.imageContent;
  }

  try {
    return await agentApi.sendAgentMessage(agentId, requestData, signal ? { signal } : undefined);
  } catch (error) {
    handleChatError(error, 'send');
    throw error;
  }
};


// ==================== CHAT ACTIONS ====================
// 检查第一个对话是否为空
const isFirstChatEmpty = () => {
  if (threads.value.length === 0) return false;
  const firstThread = threads.value[0];
  const firstThreadMessages = threadMessages.value[firstThread.id] || [];
  return firstThreadMessages.length === 0;
};

// 如果第一个对话为空，直接切换到第一个对话
const switchToFirstChatIfEmpty = async () => {
  if (threads.value.length > 0 && isFirstChatEmpty()) {
    await selectChat(threads.value[0].id);
    return true;
  }
  return false;
};

const createNewChat = async () => {
  if (!AgentValidator.validateAgentId(currentAgentId.value, '创建对话') || chatUIStore.creatingNewChat) return;

  // 如果第一个对话为空，直接切换到第一个对话而不是创建新对话
  if (await switchToFirstChatIfEmpty()) return;

  // 只有当当前对话是第一个对话且为空时，才阻止创建新对话
  const currentThreadIndex = threads.value.findIndex(thread => thread.id === currentChatId.value);
  if (currentChatId.value && conversations.value.length === 0 && currentThreadIndex === 0) return;

  chatUIStore.creatingNewChat = true;
  try {
    const newThread = await createThread(currentAgentId.value, '新的对话');
    if (newThread) {
      // 中断之前线程的流式输出（如果存在）
      const previousThreadId = chatState.currentThreadId;
      if (previousThreadId) {
        const previousThreadState = getThreadState(previousThreadId);
        if (previousThreadState?.isStreaming && previousThreadState.streamAbortController) {
          previousThreadState.streamAbortController.abort();
          previousThreadState.isStreaming = false;
          previousThreadState.streamAbortController = null;
        }
      }

      chatState.currentThreadId = newThread.id;
    }
  } catch (error) {
    handleChatError(error, 'create');
  } finally {
    chatUIStore.creatingNewChat = false;
  }
};

const selectChat = async (chatId) => {
  if (!AgentValidator.validateAgentIdWithError(currentAgentId.value, '选择对话', handleValidationError)) return;

  // 中断之前线程的流式输出（如果存在）
  const previousThreadId = chatState.currentThreadId;
  if (previousThreadId && previousThreadId !== chatId) {
    const previousThreadState = getThreadState(previousThreadId);
    if (previousThreadState?.isStreaming && previousThreadState.streamAbortController) {
      previousThreadState.streamAbortController.abort();
      previousThreadState.isStreaming = false;
      previousThreadState.streamAbortController = null;
    }
  }

  chatState.currentThreadId = chatId;
  chatUIStore.isLoadingMessages = true;
  try {
    await fetchThreadMessages({ agentId: currentAgentId.value, threadId: chatId });
  } catch (error) {
    handleChatError(error, 'load');
  } finally {
    chatUIStore.isLoadingMessages = false;
  }

  await nextTick();
  scrollController.scrollToBottomStaticForce();
  await fetchAgentState(currentAgentId.value, chatId);
};

const deleteChat = async (chatId) => {
  if (!AgentValidator.validateAgentIdWithError(currentAgentId.value, '删除对话', handleValidationError)) return;
  try {
    await deleteThread(chatId);
    if (chatState.currentThreadId === chatId) {
      chatState.currentThreadId = null;
      // 如果删除的是当前对话，自动创建新对话
      await createNewChat();
    } else if (chatsList.value.length > 0) {
      // 如果删除的不是当前对话，选择第一个可用对话
      await selectChat(chatsList.value[0].id);
    }
  } catch (error) {
    handleChatError(error, 'delete');
  }
};

const renameChat = async (data) => {
  let { chatId, title } = data;
  if (!AgentValidator.validateRenameOperation(chatId, title, currentAgentId.value, handleValidationError)) return;
  if (title.length > 30) title = title.slice(0, 30);
  try {
    await updateThread(chatId, title);
  } catch (error) {
    handleChatError(error, 'rename');
  }
};

const handleSendMessage = async ({ image } = {}) => {
  console.log('AgentChatComponent: handleSendMessage payload image:', image);
  const text = userInput.value.trim();
  if ((!text && !image) || !currentAgent.value || isProcessing.value) return;

  let threadId = currentChatId.value;
  if (!threadId) {
    threadId = await ensureActiveThread(text);
    if (!threadId) {
      message.error('创建对话失败，请重试');
      return;
    }
  }

  userInput.value = '';

  await nextTick();
  scrollController.scrollToBottom(true);

  const threadState = getThreadState(threadId);
  if (!threadState) return;

  threadState.isStreaming = true;
  resetOnGoingConv(threadId);
  threadState.streamAbortController = new AbortController();

  try {
    const response = await sendMessage({
      agentId: currentAgentId.value,
      threadId: threadId,
      text: text,
      signal: threadState.streamAbortController?.signal,
      imageData: image
    });

    await handleAgentResponse(response, threadId);
  } catch (error) {
    if (error.name !== 'AbortError') {
      console.error('Stream error:', error);
      handleChatError(error, 'send');
    } else {
      console.warn("[Interrupted] Catch");
    }
    threadState.isStreaming = false;
  } finally {
    threadState.streamAbortController = null;
    // 异步加载历史记录，保持当前消息显示直到历史记录加载完成
    fetchThreadMessages({ agentId: currentAgentId.value, threadId: threadId, delay: 500 })
    .finally(() => {
      // 历史记录加载完成后，安全地清空当前进行中的对话
      resetOnGoingConv(threadId);
      scrollController.scrollToBottom();
    });
  }
};

// 发送或中断
const handleSendOrStop = async (payload) => {
  const threadId = currentChatId.value;
  const threadState = getThreadState(threadId);
  if (isProcessing.value && threadState && threadState.streamAbortController) {
    // 中断生成
    threadState.streamAbortController.abort();

    // 中断后刷新消息历史，确保显示最新的状态
    try {
      await fetchThreadMessages({ agentId: currentAgentId.value, threadId: threadId, delay: 500 });
      message.info('已中断对话生成');
    } catch (error) {
      console.error('刷新消息历史失败:', error);
      message.info('已中断对话生成');
    }
    return;
  }
  await handleSendMessage(payload);
};

// ==================== 人工审批处理 ====================
const handleApprovalWithStream = async (approved) => {
  console.log('🔄 [STREAM] Starting resume stream processing');

  const threadId = approvalState.threadId;
  if (!threadId) {
    message.error('无效的审批请求');
    approvalState.showModal = false;
    return;
  }

  const threadState = getThreadState(threadId);
  if (!threadState) {
    message.error('无法找到对应的对话线程');
    approvalState.showModal = false;
    return;
  }

  try {
    // 使用审批 composable 处理审批
    const response = await handleApproval(approved, currentAgentId.value);

    if (!response) return; // 如果 handleApproval 抛出错误，这里不会执行

    console.log('🔄 [STREAM] Processing resume streaming response');

    // 处理流式响应
    await handleAgentResponse(response, threadId, (chunk) => {
      console.log('🔄 [STREAM] Processing chunk:', chunk);
    });

    console.log('🔄 [STREAM] Resume stream processing completed');

  } catch (error) {
    console.error('❌ [STREAM] Resume stream failed:', error);
    if (error.name !== 'AbortError') {
      console.error('Resume approval error:', error);
      // handleChatError 已在 useApproval 中调用
    }
  } finally {
    console.log('🔄 [STREAM] Cleaning up streaming state');
    if (threadState) {
      threadState.isStreaming = false;
      threadState.streamAbortController = null;
    }

    // 异步加载历史记录，保持当前消息显示直到历史记录加载完成
    fetchThreadMessages({ agentId: currentAgentId.value, threadId: threadId, delay: 500 })
    .finally(() => {
      // 历史记录加载完成后，安全地清空当前进行中的对话
      resetOnGoingConv(threadId);
      scrollController.scrollToBottom();
    });
  }
};

const handleApprove = () => {
  handleApprovalWithStream(true);
};

const handleReject = () => {
  handleApprovalWithStream(false);
};

// 处理示例问题点击
const handleExampleClick = (questionText) => {
  userInput.value = questionText;
  nextTick(() => {
    handleSendMessage();
  });
};

const buildExportPayload = () => {
  const agentId = currentAgentId.value;
  let agentDescription = '';
  if (agentId && agents.value && agents.value.length > 0) {
    const agent = agents.value.find(a => a.agent_id === agentId || a.id === agentId);
    agentDescription = agent ? (agent.description || '') : '';
  }

  const payload = {
    chatTitle: currentThread.value?.title || '新对话',
    agentName: currentAgentName.value || currentAgent.value?.name || '智能助手',
    agentDescription: agentDescription || currentAgent.value?.description || '',
    messages: conversations.value ? JSON.parse(JSON.stringify(conversations.value)) : [],
    onGoingMessages: onGoingConvMessages.value ? JSON.parse(JSON.stringify(onGoingConvMessages.value)) : []
  };

  return payload;
};

defineExpose({
  getExportPayload: buildExportPayload
});

const toggleSidebar = () => {
  chatUIStore.toggleSidebar();
};
const openAgentModal = () => emit('open-agent-modal');

const handleAgentStateRefresh = async () => {
  if (!currentAgentId.value || !currentChatId.value) return;
  await fetchAgentState(currentAgentId.value, currentChatId.value);
};

// ==================== HELPER FUNCTIONS ====================
const getLastMessage = (conv) => {
  if (!conv?.messages?.length) return null;
  for (let i = conv.messages.length - 1; i >= 0; i--) {
    if (conv.messages[i].type === 'ai') return conv.messages[i];
  }
  return null;
};

const showMsgRefs = (msg) => {
  // 如果正在审批中，不显示 refs
  if (approvalState.showModal) {
    return false;
  }

  // 如果当前线程ID与审批线程ID匹配，但审批框已关闭（说明刚刚处理完审批）
  // 且当前有新的流式处理正在进行，则不显示之前被中断的消息的 refs
  if (approvalState.threadId &&
      chatState.currentThreadId === approvalState.threadId &&
      !approvalState.showModal &&
      isProcessing) {
    return false;
  }

  // 只有真正完成的消息才显示 refs
  if (msg.isLast && msg.status === 'finished') {
    return ['copy'];
  }
  return false;
};

// ==================== LIFECYCLE & WATCHERS ====================
const loadChatsList = async () => {
  const agentId = currentAgentId.value;
  if (!agentId) {
    console.warn('No agent selected, cannot load chats list');
    threads.value = [];
    chatState.currentThreadId = null;
    return;
  }

  try {
    await fetchThreads(agentId);
    if (currentAgentId.value !== agentId) return;

    // 如果当前线程不在线程列表中，清空当前线程
    if (chatState.currentThreadId && !threads.value.find(t => t.id === chatState.currentThreadId)) {
      chatState.currentThreadId = null;
    }

    // 如果有线程但没有选中任何线程，自动选择第一个
    if (threads.value.length > 0 && !chatState.currentThreadId) {
      await selectChat(threads.value[0].id);
    }
  } catch (error) {
    handleChatError(error, 'load');
  }
};


const initAll = async () => {
  try {
    if (!agentStore.isInitialized) {
      await agentStore.initialize();
    }
  } catch (error) {
    handleChatError(error, 'load');
  }
};

onMounted(async () => {
  await initAll();
  scrollController.enableAutoScroll();
});

watch(currentAgentId, async (newAgentId, oldAgentId) => {
  if (newAgentId !== oldAgentId) {
    // 清理当前线程状态
    chatState.currentThreadId = null;
    threadMessages.value = {};
    // 清理所有线程状态
    resetOnGoingConv();

    if (newAgentId) {
      await loadChatsList();
    } else {
      threads.value = [];
    }
  }
}, { immediate: true });


watch(conversations, () => {
  if (isProcessing.value) {
    scrollController.scrollToBottom();
  }
}, { deep: true, flush: 'post' });

</script>

<style lang="less" scoped>
@import '@/assets/css/main.css';
@import '@/assets/css/animations.less';

.chat-container {
  display: flex;
  width: 100%;
  height: 100%;
  position: relative;
}

.sidebar-backdrop {
  display: none; /* 默认隐藏，通过v-if控制显示 */
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background-color: rgba(0, 0, 0, 0.4);
  z-index: 99;
  animation: fadeIn 0.3s ease;
}

.floating-sidebar {
  position: absolute !important;
  z-index: 1001;
  height: 100%;
  left: 0;
  top: 0;
  transform: translateX(0);
  transition: transform 0.3s ease;
  width: 80% !important;
  max-width: 300px;

  &.no-transition {
    transition: none !important;
  }

  &.collapsed {
    transform: translateX(-100%);
  }
}

.chat {
  position: relative;
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow-x: hidden;
  position: relative;
  box-sizing: border-box;
  overflow-y: scroll;
  transition: all 0.3s ease;

  .chat-header {
    user-select: none;
    position: sticky;
    top: 0;
    z-index: 10;
    height: var(--header-height);
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 1rem 8px;

    .header__left, .header__right {
      display: flex;
      align-items: center;
    }

    .switch-icon {
      color: var(--gray-500);
      transition: all 0.2s ease;
    }

    .agent-nav-btn:hover .switch-icon {
      color: var(--main-500);
    }
  }
}

.chat-examples {
  padding: 0 50px;
  text-align: center;
  position: absolute;
  bottom: 65%;
  width: 100%;
  z-index: 9;
  animation: slideInUp 0.5s ease-out;

  h1 {
    margin-bottom: 20px;
    font-size: 1.3rem;
    color: var(--gray-1000);
  }

  p {
    font-size: 1.1rem;
    color: var(--gray-700);
  }

  .agent-icons {
    height: 180px;
  }
}

.example-questions {
  margin-top: 16px;
  text-align: center;

  .example-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    justify-content: center;
  }

  .example-chip {
    padding: 6px 12px;
    background: var(--gray-25);
    // border: 1px solid var(--gray-100);
    border-radius: 16px;
    cursor: pointer;
    font-size: 0.8rem;
    color: var(--gray-700);
    transition: all 0.15s ease;
    white-space: nowrap;
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;

    &:hover {
      // background: var(--main-25);
      border-color: var(--main-200);
      color: var(--main-700);
      box-shadow: 0 0px 4px rgba(0, 0, 0, 0.03);
    }

    &:active {
      transform: translateY(0);
      box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
    }
  }
}

.chat-loading {
  padding: 0 50px;
  text-align: center;
  position: absolute;
  top: 20%;
  width: 100%;
  z-index: 9;
  animation: slideInUp 0.5s ease-out;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;

  span {
    color: var(--gray-700);
    font-size: 14px;
  }

  .loading-spinner {
    width: 20px;
    height: 20px;
    border: 2px solid var(--gray-200);
    border-top-color: var(--main-color);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
  }
}

.chat-box {
  width: 100%;
  max-width: 800px;
  margin: 0 auto;
  flex-grow: 1;
  padding: 1rem 2rem;
  display: flex;
  flex-direction: column;
}

.conv-box {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.bottom {
  position: sticky;
  bottom: 0;
  width: 100%;
  margin: 0 auto;
  padding: 4px 2rem 0 2rem;
  background: var(--gray-0);
  z-index: 1000;

  .message-input-wrapper {
    width: 100%;
    max-width: 800px;
    margin: 0 auto;

    .bottom-actions {
      display: flex;
      justify-content: center;
      align-items: center;
    }

    .note {
      font-size: small;
      color: var(--gray-300);
      margin: 4px 0;
      user-select: none;
    }
  }

  &.start-screen {
    position: absolute;
    top: 45%;
    left: 50%;
    transform: translate(-50%, -50%);
    bottom: auto;
    max-width: 800px;
    width: 90%;
    background: transparent;
    padding: 0;
    border-top: none;
    z-index: 100; /* Ensure it's above other elements */
  }
}

.loading-dots {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 3px;
}

.loading-dots div {
  width: 6px;
  height: 6px;
  background: linear-gradient(135deg, var(--main-color), var(--main-700));
  border-radius: 50%;
  animation: dotPulse 1.4s infinite ease-in-out both;
}

.loading-dots div:nth-child(1) {
  animation-delay: -0.32s;
}

.loading-dots div:nth-child(2) {
  animation-delay: -0.16s;
}

.loading-dots div:nth-child(3) {
  animation-delay: 0s;
}

.generating-status {
  display: flex;
  justify-content: flex-start;
  padding: 1rem 0;
  animation: fadeInUp 0.4s ease-out;
  transition: all 0.2s;
}

.generating-indicator {
  display: flex;
  align-items: center;
  padding: 0.75rem 0rem;

  .generating-text {
    margin-left: 12px;
    font-size: 14px;
    font-weight: 500;
    letter-spacing: 0.025em;
    /* 恢复灰色调：深灰 -> 亮灰(高光) -> 深灰 */
    background: linear-gradient(
      90deg,
      var(--gray-700) 0%,
      var(--gray-700) 40%,
      var(--gray-300) 45%,
      var(--gray-200) 50%,
      var(--gray-300) 55%,
      var(--gray-700) 60%,
      var(--gray-700) 100%
    );
    background-size: 200% auto;
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    animation: waveFlash 2s linear infinite;
  }
}

@keyframes waveFlash {
  0% {
    background-position: 200% center;
  }
  100% {
    background-position: -200% center;
  }
}


@media (max-width: 1800px) {

  .chat-header {
    background-color: var(--gray-0);
    border-bottom: 1px solid var(--gray-100);
  }
}



@media (max-width: 768px) {
  .chat-sidebar.collapsed {
    width: 0;
    border: none;
  }

  .chat-header {
    .header__left {
      .text {
        display: none;
      }
    }
  }
}

@media (max-width: 520px) {
  .sidebar-backdrop {
    display: block;
  }

  .chat-box {
    padding: 1rem 1rem;
  }

  .bottom {
    padding: 0.5rem 0.5rem;
  }

  .chat-header {
    padding: 0.5rem 0 !important;

  }

  .floating-sidebar {
    position: fixed;
    z-index: 100;
    height: 100%;
    left: 0;
    top: 0;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
    transform: translateX(0);
    transition: transform 0.3s ease;
    width: 80% !important;
    max-width: 300px;

    &.collapsed {
      transform: translateX(-100%);
    }
  }
}

.hide-text {
  display: none;
}
</style>

<style lang="less">
.agent-nav-btn {
  display: flex;
  gap: 10px;
  padding: 6px 14px;
  justify-content: center;
  align-items: center;
  border-radius: 12px;
  color: var(--gray-900);
  cursor: pointer;
  width: auto;
  font-size: 15px;
  transition: background-color 0.3s;
  border: none;
  background: transparent;

  &:hover:not(.is-disabled) {
    background-color: var(--gray-50);
  }

  &.is-disabled {
    cursor: not-allowed;
    opacity: 0.7;
    pointer-events: none;
  }

  .nav-btn-icon {
    height: 24px;
  }

  .loading-icon {
    animation: spin 1s linear infinite;
  }
}

/* AgentState 按钮有内容时的样式 */
.agent-nav-btn.agent-state-btn.has-content:hover:not(.is-disabled) {
  color: var(--main-700);
  background-color: var(--main-20);
}

</style>