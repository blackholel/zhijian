<template>
  <div class="agent-list-section">
    <div class="section-header" @click="toggleExpand">
      <ChevronRight :size="16" class="expand-icon" :class="{ expanded: isExpanded }" />
      <span class="section-title">智能体</span>
      <button class="add-btn" @click.stop="$emit('create-agent')" title="创建智能体">
        <Plus :size="16" />
      </button>
    </div>

    <div class="agent-groups" v-show="isExpanded">
      <!-- 系统智能体 -->
      <div class="agent-group" v-if="builtinAgents.length > 0">
        <div class="group-header" @click="toggleGroup('builtin')">
          <ChevronRight :size="14" class="group-icon" :class="{ expanded: expandedGroups.builtin }" />
          <span class="group-title">系统智能体</span>
          <span class="group-count">{{ builtinAgents.length }}</span>
        </div>
        <div class="group-items" v-show="expandedGroups.builtin">
          <div
            v-for="agent in builtinAgents"
            :key="agent.agent_id"
            class="agent-item"
            :class="{ active: selectedAgentId === agent.agent_id }"
            @click="$emit('select-agent', agent.agent_id)"
          >
            <span class="agent-icon">{{ agent.icon || '🤖' }}</span>
            <span class="agent-name">{{ agent.name }}</span>
          </div>
        </div>
      </div>

      <!-- 我的智能体 -->
      <div class="agent-group">
        <div class="group-header" @click="toggleGroup('my')">
          <ChevronRight :size="14" class="group-icon" :class="{ expanded: expandedGroups.my }" />
          <span class="group-title">我的智能体</span>
          <span class="group-count">{{ myAgents.length }}</span>
        </div>
        <div class="group-items" v-show="expandedGroups.my">
          <div
            v-for="agent in myAgents"
            :key="agent.agent_id"
            class="agent-item"
            :class="{ active: selectedAgentId === agent.agent_id }"
            @click="$emit('select-agent', agent.agent_id)"
          >
            <span class="agent-icon">{{ agent.icon || '🤖' }}</span>
            <span class="agent-name">{{ agent.name }}</span>
            <a-dropdown :trigger="['click']" @click.stop>
              <template #overlay>
                <a-menu>
                  <a-menu-item key="edit" @click.stop="$emit('edit-agent', agent.agent_id)">
                    <EditOutlined /> 编辑
                  </a-menu-item>
                  <a-menu-item key="duplicate" @click.stop="$emit('duplicate-agent', agent.agent_id)">
                    <CopyOutlined /> 复制
                  </a-menu-item>
                  <a-menu-item key="delete" @click.stop="$emit('delete-agent', agent.agent_id)">
                    <DeleteOutlined /> 删除
                  </a-menu-item>
                </a-menu>
              </template>
              <button class="more-btn" @click.stop>
                <MoreOutlined />
              </button>
            </a-dropdown>
          </div>
          <div v-if="myAgents.length === 0" class="empty-hint">
            点击 + 创建智能体
          </div>
        </div>
      </div>

      <!-- 公开智能体 -->
      <div class="agent-group" v-if="publicAgents.length > 0">
        <div class="group-header" @click="toggleGroup('public')">
          <ChevronRight :size="14" class="group-icon" :class="{ expanded: expandedGroups.public }" />
          <span class="group-title">公开智能体</span>
          <span class="group-count">{{ publicAgents.length }}</span>
        </div>
        <div class="group-items" v-show="expandedGroups.public">
          <div
            v-for="agent in publicAgents"
            :key="agent.agent_id"
            class="agent-item"
            :class="{ active: selectedAgentId === agent.agent_id }"
            @click="$emit('select-agent', agent.agent_id)"
          >
            <span class="agent-icon">{{ agent.icon || '🤖' }}</span>
            <span class="agent-name">{{ agent.name }}</span>
            <a-dropdown :trigger="['click']" @click.stop>
              <template #overlay>
                <a-menu>
                  <a-menu-item key="duplicate" @click.stop="$emit('duplicate-agent', agent.agent_id)">
                    <CopyOutlined /> 复制
                  </a-menu-item>
                </a-menu>
              </template>
              <button class="more-btn" @click.stop>
                <MoreOutlined />
              </button>
            </a-dropdown>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue';
import { ChevronRight, Plus } from 'lucide-vue-next';
import { EditOutlined, DeleteOutlined, CopyOutlined, MoreOutlined } from '@ant-design/icons-vue';

defineProps({
  builtinAgents: {
    type: Array,
    default: () => []
  },
  myAgents: {
    type: Array,
    default: () => []
  },
  publicAgents: {
    type: Array,
    default: () => []
  },
  selectedAgentId: {
    type: String,
    default: null
  }
});

defineEmits(['select-agent', 'create-agent', 'edit-agent', 'delete-agent', 'duplicate-agent']);

const isExpanded = ref(true);
const expandedGroups = reactive({
  builtin: true,
  my: true,
  public: false
});

function toggleExpand() {
  isExpanded.value = !isExpanded.value;
}

function toggleGroup(group) {
  expandedGroups[group] = !expandedGroups[group];
}
</script>

<style lang="less" scoped>
.agent-list-section {
  padding: 8px 0;
  border-bottom: 1px solid var(--gray-200);
}

.section-header {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  cursor: pointer;
  user-select: none;

  &:hover {
    background: var(--gray-100);
  }

  .expand-icon {
    transition: transform 0.2s;
    color: var(--gray-500);

    &.expanded {
      transform: rotate(90deg);
    }
  }

  .section-title {
    flex: 1;
    margin-left: 4px;
    font-size: 13px;
    font-weight: 500;
    color: var(--gray-700);
  }

  .add-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border: none;
    background: transparent;
    border-radius: 4px;
    cursor: pointer;
    color: var(--gray-500);

    &:hover {
      background: var(--gray-200);
      color: var(--gray-700);
    }
  }
}

.agent-groups {
  padding: 0 8px;
}

.agent-group {
  margin-bottom: 4px;

  .group-header {
    display: flex;
    align-items: center;
    padding: 6px 8px;
    cursor: pointer;
    border-radius: 4px;

    &:hover {
      background: var(--gray-100);
    }

    .group-icon {
      transition: transform 0.2s;
      color: var(--gray-400);

      &.expanded {
        transform: rotate(90deg);
      }
    }

    .group-title {
      flex: 1;
      margin-left: 4px;
      font-size: 12px;
      color: var(--gray-500);
    }

    .group-count {
      font-size: 11px;
      color: var(--gray-400);
      background: var(--gray-100);
      padding: 1px 6px;
      border-radius: 10px;
    }
  }

  .group-items {
    padding-left: 12px;
  }
}

.agent-item {
  display: flex;
  align-items: center;
  padding: 8px 10px;
  margin: 2px 0;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;

  &:hover {
    background: var(--gray-100);

    .more-btn {
      opacity: 1;
    }
  }

  &.active {
    background: var(--color-primary-50);

    .agent-name {
      color: var(--color-primary-700);
      font-weight: 500;
    }
  }

  .agent-icon {
    font-size: 16px;
    margin-right: 8px;
  }

  .agent-name {
    flex: 1;
    font-size: 13px;
    color: var(--gray-700);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .more-btn {
    display: flex;
    align-items: center;
    justify-content: center;
    width: 24px;
    height: 24px;
    border: none;
    background: transparent;
    border-radius: 4px;
    cursor: pointer;
    color: var(--gray-400);
    opacity: 0;
    transition: opacity 0.15s;

    &:hover {
      background: var(--gray-200);
      color: var(--gray-600);
    }
  }
}

.empty-hint {
  padding: 12px 10px;
  font-size: 12px;
  color: var(--gray-400);
  text-align: center;
}
</style>
