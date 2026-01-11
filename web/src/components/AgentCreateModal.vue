<template>
  <a-modal
    v-model:open="visible"
    :title="isEdit ? '编辑智能体' : '创建智能体'"
    :width="560"
    :destroyOnClose="true"
    @ok="handleSubmit"
    @cancel="handleCancel"
    :confirmLoading="loading"
  >
    <a-form
      ref="formRef"
      :model="formData"
      :rules="rules"
      layout="vertical"
      class="agent-form"
    >
      <a-form-item label="名称" name="name">
        <a-input v-model:value="formData.name" placeholder="输入智能体名称" :maxlength="128" />
      </a-form-item>

      <a-form-item label="描述" name="description">
        <a-textarea
          v-model:value="formData.description"
          placeholder="描述智能体的功能和用途"
          :rows="2"
          :maxlength="500"
        />
      </a-form-item>

      <a-form-item label="图标" name="icon">
        <a-input v-model:value="formData.icon" placeholder="输入 emoji 或图标 URL" />
      </a-form-item>

      <a-form-item label="系统提示词" name="system_prompt">
        <a-textarea
          v-model:value="formData.system_prompt"
          placeholder="定义智能体的行为和角色"
          :rows="4"
          :maxlength="10000"
        />
      </a-form-item>

      <a-form-item label="底层智能体" name="base_agent_id">
        <a-select
          v-model:value="formData.base_agent_id"
          placeholder="选择底层智能体"
          :options="baseAgentOptions"
          :loading="loadingBaseAgents"
        />
      </a-form-item>

      <a-form-item label="关联知识库" name="knowledges">
        <a-select
          v-model:value="formData.knowledges"
          mode="multiple"
          placeholder="选择要关联的知识库"
          :options="knowledgeOptions"
        />
      </a-form-item>

      <a-form-item label="MCP 服务器" name="mcps">
        <a-select
          v-model:value="formData.mcps"
          mode="multiple"
          placeholder="选择要启用的 MCP 服务器"
          :options="mcpOptions"
        />
      </a-form-item>

      <a-form-item label="可见性" name="visibility">
        <a-radio-group v-model:value="formData.visibility">
          <a-radio value="private">私有</a-radio>
          <a-radio value="public">公开</a-radio>
        </a-radio-group>
      </a-form-item>
    </a-form>
  </a-modal>
</template>

<script setup>
import { ref, reactive, watch, computed } from 'vue';
import { message } from 'ant-design-vue';
import { useAgentStore } from '@/stores/agent';
import { databaseApi } from '@/apis/knowledge_api';
import { listMyConfigs } from '@/apis/mcp_api';
import { agentManageApi } from '@/apis/agent_api';

const props = defineProps({
  open: {
    type: Boolean,
    default: false
  },
  agentId: {
    type: String,
    default: null
  }
});
const emit = defineEmits(['update:open', 'success']);

const agentStore = useAgentStore();
const formRef = ref(null);
const loading = ref(false);

// 选项列表
const knowledgeOptions = ref([]);
const mcpOptions = ref([]);
const baseAgentOptions = ref([]);
const loadingBaseAgents = ref(false);

const visible = computed({
  get: () => props.open,
  set: (val) => emit('update:open', val)
});

const isEdit = computed(() => !!props.agentId);

const formData = reactive({
  name: '',
  description: '',
  icon: '',
  system_prompt: '',
  base_agent_id: 'ChatbotAgent',
  knowledges: [],
  mcps: [],
  visibility: 'private'
});

const rules = {
  name: [
    { required: true, message: '请输入智能体名称', trigger: 'blur' },
    { min: 1, max: 128, message: '名称长度为 1-128 个字符', trigger: 'blur' }
  ],
  base_agent_id: [
    { required: true, message: '请选择底层智能体', trigger: 'change' }
  ]
};

// 获取知识库列表
async function fetchKnowledges() {
  try {
    const res = await databaseApi.getDatabases();
    knowledgeOptions.value = (res.databases || []).map(db => ({
      label: db.name,
      value: db.id
    }));
  } catch (err) {
    console.error('Failed to fetch knowledges:', err);
  }
}

// 获取 MCP 配置列表
async function fetchMcpConfigs() {
  try {
    const res = await listMyConfigs();
    // API 直接返回数组，不是 { configs: [] }
    const configs = Array.isArray(res) ? res : (res.configs || []);
    mcpOptions.value = configs.map(config => ({
      label: config.custom_name || config.tool?.name || config.mcp_id,
      value: `user_${config.id}`
    }));
  } catch (err) {
    console.error('Failed to fetch MCP configs:', err);
  }
}

// 获取底层智能体列表
async function fetchBaseAgents() {
  try {
    loadingBaseAgents.value = true;
    const res = await agentManageApi.listBaseAgents();
    baseAgentOptions.value = (res.base_agents || []).map(agent => ({
      label: `${agent.name} (${agent.id})`,
      value: agent.id
    }));
  } catch (err) {
    console.error('Failed to fetch base agents:', err);
    // 降级使用默认选项
    baseAgentOptions.value = [
      { label: '智能体助手 (ChatbotAgent)', value: 'ChatbotAgent' }
    ];
  } finally {
    loadingBaseAgents.value = false;
  }
}

// 弹窗打开时加载数据
watch(() => props.open, async (newOpen) => {
  if (newOpen) {
    // 并行加载所有选项列表
    await Promise.all([
      fetchKnowledges(),
      fetchMcpConfigs(),
      fetchBaseAgents(),
      props.agentId ? loadAgentData(props.agentId) : Promise.resolve()
    ]);
  } else {
    resetForm();
  }
}, { immediate: true });

async function loadAgentData(agentId) {
  try {
    loading.value = true;
    const agent = await agentStore.getAgentForEdit(agentId);
    Object.assign(formData, {
      name: agent.name || '',
      description: agent.description || '',
      icon: agent.icon || '',
      system_prompt: agent.system_prompt || '',
      base_agent_id: agent.base_agent_id || 'ChatbotAgent',
      knowledges: agent.knowledges || [],
      mcps: agent.mcps || [],
      visibility: agent.visibility || 'private'
    });
  } catch (err) {
    message.error('加载智能体数据失败');
  } finally {
    loading.value = false;
  }
}

function resetForm() {
  Object.assign(formData, {
    name: '',
    description: '',
    icon: '',
    system_prompt: '',
    base_agent_id: 'ChatbotAgent',
    knowledges: [],
    mcps: [],
    visibility: 'private'
  });
  formRef.value?.resetFields();
}

async function handleSubmit() {
  try {
    await formRef.value?.validate();
    loading.value = true;

    const data = { ...formData };

    if (isEdit.value) {
      await agentStore.updateCustomAgent(props.agentId, data);
      message.success('智能体更新成功');
    } else {
      await agentStore.createAgent(data);
      message.success('智能体创建成功');
    }

    emit('success');
    visible.value = false;
  } catch (err) {
    if (err.errorFields) {
      // 表单验证错误
      return;
    }
    message.error(isEdit.value ? '更新失败' : '创建失败');
  } finally {
    loading.value = false;
  }
}

function handleCancel() {
  visible.value = false;
}
</script>

<style lang="less" scoped>
.agent-form {
  max-height: 60vh;
  overflow-y: auto;
  padding-right: 8px;

  :deep(.ant-form-item) {
    margin-bottom: 16px;
  }

  :deep(.ant-form-item-label) {
    padding-bottom: 4px;

    > label {
      font-size: 13px;
      color: var(--gray-700);
    }
  }
}
</style>
