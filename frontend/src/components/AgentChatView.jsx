import React, { useState, useEffect, useRef } from 'react';
import { Send, Bot, User, ShieldAlert, ArrowLeft, CheckCircle2, XCircle, Clock } from 'lucide-react';
import { api } from '../services/api';

export default function AgentChatView({
  ticket,
  chatMessages = [],
  onBackToReview,
  onRefreshTicket
}) {
  const [messages, setMessages] = useState(chatMessages);
  const [inputText, setInputText] = useState('');
  const [isSending, setIsSending] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    setMessages(chatMessages);
  }, [chatMessages]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSendMessage = async (e, approveExternal = false) => {
    if (e) e.preventDefault();
    const content = inputText.trim() || (approveExternal ? 'I approve granting external network access.' : '');
    if (!content) return;

    setIsSending(true);
    try {
      const newMsg = await api.sendChatMessage(ticket.id, content, approveExternal);
      setMessages((prev) => [...prev, newMsg]);
      setInputText('');
      if (onRefreshTicket) onRefreshTicket();
    } catch (err) {
      console.error('Error sending message to agent:', err);
    } finally {
      setIsSending(false);
    }
  };

  const isPausedWaitingInput = ticket.status === 'paused_waiting_input';

  return (
    <div className="flex-1 flex flex-col h-[calc(100vh-3.5rem)] bg-slate-950">
      {/* Chat Header */}
      <div className="px-6 py-3.5 bg-slate-900 border-b border-slate-800 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={onBackToReview}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
            title="Back to Review Queue"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-xs font-bold px-2 py-0.5 rounded bg-slate-800 text-slate-200">
                {ticket.jira_key}
              </span>
              <h3 className="font-bold text-slate-100 text-sm">{ticket.title}</h3>
            </div>
            <span className="text-[11px] text-slate-400">
              Interactive Coding Agent Channel &bull; Branch: {ticket.branch_name}
            </span>
          </div>
        </div>

        {isPausedWaitingInput && (
          <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-rose-950 border border-rose-800 text-rose-300 text-xs font-semibold animate-pulse">
            <ShieldAlert className="w-4 h-4 text-rose-400" />
            Agent Paused: Awaiting User Response
          </div>
        )}
      </div>

      {/* Messages Scroll Area */}
      <div className="flex-1 overflow-y-auto p-6 space-y-4">
        {messages.length === 0 ? (
          <div className="py-20 text-center text-slate-500 text-xs">
            No previous chat messages for this ticket. The agent will post clarifying questions here.
          </div>
        ) : (
          messages.map((msg) => {
            const isAgent = msg.sender === 'agent';
            const isPendingQuestion = isAgent && msg.status === 'pending';

            return (
              <div
                key={msg.id}
                className={`flex gap-3 max-w-2xl ${isAgent ? 'mr-auto' : 'ml-auto flex-row-reverse'}`}
              >
                <div
                  className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 shadow ${
                    isAgent
                      ? 'bg-purple-900/60 text-purple-300 border border-purple-700'
                      : 'bg-orange-600 text-white'
                  }`}
                >
                  {isAgent ? <Bot className="w-4 h-4" /> : <User className="w-4 h-4" />}
                </div>

                <div className="space-y-1">
                  <div
                    className={`flex items-center gap-2 text-[10px] text-slate-500 ${
                      isAgent ? '' : 'justify-end'
                    }`}
                  >
                    <span className="font-semibold capitalize text-slate-400">
                      {isAgent ? 'Coding Agent' : 'You'}
                    </span>
                    <span>
                      {new Date(msg.created_at).toLocaleTimeString([], {
                        hour: '2-digit',
                        minute: '2-digit'
                      })}
                    </span>
                  </div>

                  <div
                    className={`p-4 rounded-2xl text-xs leading-relaxed shadow-md ${
                      isAgent
                        ? isPendingQuestion
                          ? 'bg-rose-950/40 border border-rose-800 text-slate-200'
                          : 'bg-slate-900 border border-slate-800 text-slate-200'
                        : 'bg-orange-600 text-white rounded-tr-none'
                    }`}
                  >
                    {msg.content}
                  </div>

                  {/* If this is a pending question requiring external access approval, show quick action bar */}
                  {isPendingQuestion && isPausedWaitingInput && (
                    <div className="pt-2 flex items-center gap-2">
                      <button
                        onClick={() => handleSendMessage(null, true)}
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white flex items-center gap-1.5 shadow transition cursor-pointer"
                      >
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        Grant Network Access & Resume
                      </button>
                      <button
                        onClick={() => {
                          setInputText('Do not access external network. Please mock all external responses locally.');
                        }}
                        className="px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-rose-300 border border-slate-700 flex items-center gap-1.5 transition"
                      >
                        <XCircle className="w-3.5 h-3.5" />
                        Deny & Use Local Mock
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input Box */}
      <div className="p-4 bg-slate-900 border-t border-slate-800 shrink-0">
        <form onSubmit={handleSendMessage} className="flex gap-2">
          <input
            type="text"
            placeholder="Type your response to the coding agent..."
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            className="flex-1 bg-slate-950 border border-slate-800 rounded-xl px-4 py-2.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-orange-500"
          />
          <button
            type="submit"
            disabled={!inputText.trim() || isSending}
            className="px-5 py-2.5 rounded-xl text-xs font-bold bg-orange-600 hover:bg-orange-500 disabled:bg-slate-800 text-white shadow-lg shadow-orange-600/20 flex items-center gap-2 transition cursor-pointer"
          >
            <Send className="w-3.5 h-3.5" />
            {isSending ? 'Sending...' : 'Send'}
          </button>
        </form>
      </div>
    </div>
  );
}
