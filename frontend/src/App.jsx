import React, { useState, useEffect } from 'react';
import Header from './components/Header';
import LeftSidebar from './components/LeftSidebar';
import ReviewQueue from './components/ReviewQueue';
import QueueHistoryView from './components/QueueHistoryView';
import ProjectDetailsView from './components/ProjectDetailsView';
import AgentChatView from './components/AgentChatView';
import RunDashboard from './components/RunDashboard';
import WorkLogModal from './components/WorkLogModal';
import MergeConfirmModal from './components/MergeConfirmModal';
import { api, connectWebSocket } from './services/api';

export default function App() {
  // Navigation & View State
  const [currentView, setCurrentView] = useState('runs-dashboard'); // 'ticket-review' | 'queue-history' | 'project-details' | 'ticket-chat'
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);

  // Selected Entities
  const [selectedProjectId, setSelectedProjectId] = useState(null);
  const [selectedTicketId, setSelectedTicketId] = useState(null);
  const [selectedWorkLogId, setSelectedWorkLogId] = useState(null);
  const [mergeModalTicket, setMergeModalTicket] = useState(null);

  // Data Store
  const [projects, setProjects] = useState([]);
  const [projectTickets, setProjectTickets] = useState({});
  const [recentActions, setRecentActions] = useState([]);
  const [notificationData, setNotificationData] = useState({
    icon_status: 'normal',
    needs_input_count: 0,
    completed_count: 0,
    notifications: []
  });

  // Active Ticket Data
  const [activeTicketData, setActiveTicketData] = useState({
    ticket: null,
    work_logs: [],
    chat_messages: []
  });

  // Fetch Core Workspace Data
  const refreshProjects = async () => {
    try {
      const projList = await api.getProjects();
      setProjects(projList);

      // Load tickets for each project
      const ticketsMap = {};
      for (const p of projList) {
        const tList = await api.getTicketsByProject(p.id);
        ticketsMap[p.id] = tList;
      }
      setProjectTickets(ticketsMap);

      // Default select first ticket if none selected
      if (!selectedTicketId && projList.length > 0) {
        const firstProjTickets = ticketsMap[projList[0].id] || [];
        if (firstProjTickets.length > 0) {
          setSelectedTicketId(firstProjTickets[0].id);
          setSelectedProjectId(projList[0].id);
        } else {
          setSelectedProjectId(projList[0].id);
        }
      }
    } catch (e) {
      console.error('Error fetching projects & tickets:', e);
    }
  };

  const refreshRecentActions = async () => {
    try {
      const data = await api.getRecentActions();
      setRecentActions(data);
    } catch (e) {
      console.error('Error fetching recent actions:', e);
    }
  };

  const refreshNotifications = async () => {
    try {
      const data = await api.getNotifications();
      setNotificationData(data);
    } catch (e) {
      console.error('Error fetching notifications:', e);
    }
  };

  const refreshActiveTicket = async () => {
    if (!selectedTicketId) return;
    try {
      const data = await api.getTicket(selectedTicketId);
      setActiveTicketData(data);
    } catch (e) {
      console.error('Error fetching active ticket:', e);
    }
  };

  // Initial Load
  useEffect(() => {
    refreshProjects();
    refreshRecentActions();
    refreshNotifications();
  }, []);

  // Update Active Ticket when selectedTicketId changes
  useEffect(() => {
    refreshActiveTicket();
  }, [selectedTicketId]);

  // Real-Time WebSocket Connection
  useEffect(() => {
    const socket = connectWebSocket((event) => {
      console.log('[WebSocket Event Received]:', event.type);
      refreshNotifications();
      refreshRecentActions();
      refreshProjects();
      if (selectedTicketId) {
        refreshActiveTicket();
      }
    });

    return () => {
      if (socket) socket.close();
    };
  }, [selectedTicketId]);

  // Handlers
  const handleSelectProject = (projectId) => {
    setSelectedProjectId(projectId);
    setCurrentView('project-details');
  };

  const handleSelectTicket = (ticketId) => {
    setSelectedTicketId(ticketId);
    setCurrentView('ticket-review');
  };

  const handleViewQueueHistory = () => {
    setCurrentView('queue-history');
  };

  const handleSubmitPromptUpdate = async (ticketId, prompt) => {
    await api.submitPromptUpdate(ticketId, prompt);
    refreshActiveTicket();
    refreshRecentActions();
    refreshNotifications();
  };

  const handleConfirmMerge = async (ticketId) => {
    await api.mergeBranch(ticketId);
    refreshActiveTicket();
    refreshProjects();
    refreshRecentActions();
  };

  return (
    <div className="flex flex-col h-screen w-screen bg-slate-950 text-slate-100 overflow-hidden font-sans">
      {/* Top Header */}
      <Header
        notificationData={notificationData}
        onRefreshNotifications={refreshNotifications}
        onSelectTicket={(ticketId) => {
          setSelectedTicketId(ticketId);
          setCurrentView('ticket-chat');
        }}
        onSelectWorkLog={(workLogId) => setSelectedWorkLogId(workLogId)}
      />

      {/* Main App Workspace Layout */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left Collapsible Column */}
        <LeftSidebar
          isCollapsed={isSidebarCollapsed}
          onToggleCollapse={() => setIsSidebarCollapsed(!isSidebarCollapsed)}
          projects={projects}
          projectTickets={projectTickets}
          recentActions={recentActions}
          selectedProjectId={selectedProjectId}
          selectedTicketId={selectedTicketId}
          currentView={currentView}
          onSelectProject={handleSelectProject}
          onSelectTicket={handleSelectTicket}
          onViewQueueHistory={handleViewQueueHistory}
          onViewRunsDashboard={() => setCurrentView('runs-dashboard')}
          onSelectWorkLog={(id) => setSelectedWorkLogId(id)}
        />

        {/* Dynamic Center Panel */}
        <main className="flex-1 flex flex-col overflow-hidden bg-slate-950">
                    {currentView === 'runs-dashboard' && (
            <RunDashboard />
          )}

          {currentView === 'ticket-review' && (
            <ReviewQueue
              ticket={activeTicketData.ticket}
              workLogs={activeTicketData.work_logs}
              chatMessages={activeTicketData.chat_messages}
              onSelectWorkLog={(id) => setSelectedWorkLogId(id)}
              onSubmitPromptUpdate={handleSubmitPromptUpdate}
              onOpenMergeModal={(ticket) => setMergeModalTicket(ticket)}
              onSwitchToChat={() => setCurrentView('ticket-chat')}
            />
          )}

          {currentView === 'queue-history' && (
            <QueueHistoryView
              onSelectWorkLog={(id) => setSelectedWorkLogId(id)}
              onSelectTicket={(ticketId) => {
                setSelectedTicketId(ticketId);
                setCurrentView('ticket-review');
              }}
            />
          )}

          {currentView === 'project-details' && (
            <ProjectDetailsView
              projectId={selectedProjectId}
              onProjectUpdated={() => {
                refreshProjects();
                refreshActiveTicket();
              }}
            />
          )}

          {currentView === 'ticket-chat' && (
            <AgentChatView
              ticket={activeTicketData.ticket || { id: selectedTicketId, jira_key: 'CHAT', title: 'Interactive Chat' }}
              chatMessages={activeTicketData.chat_messages}
              onBackToReview={() => setCurrentView('ticket-review')}
              onRefreshTicket={() => {
                refreshActiveTicket();
                refreshNotifications();
              }}
            />
          )}
        </main>
      </div>

      {/* Full Work Log Entry Modal */}
      {selectedWorkLogId && (
        <WorkLogModal
          workLogId={selectedWorkLogId}
          onClose={() => setSelectedWorkLogId(null)}
        />
      )}

      {/* Branch Merge Confirmation Modal */}
      {mergeModalTicket && (
        <MergeConfirmModal
          ticket={mergeModalTicket}
          isOpen={!!mergeModalTicket}
          onClose={() => setMergeModalTicket(null)}
          onConfirmMerge={handleConfirmMerge}
        />
      )}
    </div>
  );
}
