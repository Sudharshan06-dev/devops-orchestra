import { CommonModule } from '@angular/common';
import { Component, ViewChild, ElementRef, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  id: string;
}

interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
}

@Component({
  selector: 'app-chat-interface',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './chat-interface.component.html',
  styleUrl: './chat-interface.component.css'
})
export class ChatInterfaceComponent implements OnInit {

  // Core properties
  public chatSessions: ChatSession[] = [];
  public activeSessionId: string = '';
  public currentMessages: ChatMessage[] = [];
  public userInput: string = '';
  public isOnline: boolean = true;
  public isTyping: boolean = false;
  public textareaRows: number = 1;
  public showSuggestions: boolean = false;
  public inputStatus: string = '';

  // Suggestions
  public suggestions: string[] = [
    'Analyze my AWS infrastructure',
    'Check ECS service health',
    'Review Terraform configuration',
    'Troubleshoot deployment issues',
    'Monitor application performance',
    'Security audit checklist'
  ];

  public inputSuggestions: string[] = [
    'Why is my ECS service failing?',
    'How to optimize Lambda costs?',
    'Check CloudWatch logs for errors',
    'Setup auto-scaling for my app'
  ];

  @ViewChild('scrollContainer') scrollContainer!: ElementRef;
  @ViewChild('messageInput') messageInput!: ElementRef;

  constructor() {}

  ngOnInit(): void {
    this.initializeMockData();
    this.selectSession(this.chatSessions[0].id);
  }

  // Initialize mock data
  private initializeMockData(): void {
    this.chatSessions = [
      {
        id: 'session-1',
        title: 'AWS Infrastructure Analysis',
        messages: [
          {
            id: '1',
            role: 'user',
            content: 'Can you analyze my AWS infrastructure setup?',
            timestamp: new Date()
          },
          {
            id: '2',
            role: 'assistant',
            content: 'I\'d be happy to help analyze your AWS infrastructure! To provide the most accurate analysis, I\'ll need some information about your current setup.',
            timestamp: new Date()
          }
        ]
      },
      {
        id: 'session-2',
        title: 'ECS 502 Gateway Timeout',
        messages: [
          {
            id: '3',
            role: 'user',
            content: 'I keep getting 502 Gateway Timeout errors on my ECS service.',
            timestamp: new Date()
          },
          {
            id: '4',
            role: 'assistant',
            content: 'A 502 Gateway Timeout in ECS typically indicates issues between your load balancer and containers. Let me help you troubleshoot this.',
            timestamp: new Date()
          }
        ]
      },
      {
        id: 'session-3',
        title: 'Terraform Configuration',
        messages: [
          {
            id: '5',
            role: 'user',
            content: 'My Terraform deployment is failing. What should I check?',
            timestamp: new Date()
          }
        ]
      }
    ];
  }

  // Session management
  startNewChat(): void {
    const newId = 'chat-' + Date.now();
    const newSession: ChatSession = {
      id: newId,
      title: 'New Chat',
      messages: []
    };
    this.chatSessions.unshift(newSession);
    this.selectSession(newId);
  }

  selectSession(sessionId: string): void {
    const session = this.chatSessions.find(s => s.id === sessionId);
    if (session) {
      this.currentMessages = session.messages;
      this.activeSessionId = sessionId;
      setTimeout(() => this.scrollToBottom(), 0);
    }
  }

  deleteSession(sessionId: string, event: Event): void {
    event.stopPropagation();
    const index = this.chatSessions.findIndex(s => s.id === sessionId);
    if (index > -1) {
      this.chatSessions.splice(index, 1);
    }
  }

  // Message handling
  sendMessage(): void {
    if (!this.canSend()) return;

    const session = this.chatSessions.find(s => s.id === this.activeSessionId);
    if (!session) return;

    const userMessage: ChatMessage = {
      id: 'msg-' + Date.now(),
      role: 'user',
      content: this.userInput.trim(),
      timestamp: new Date()
    };

    session.messages.push(userMessage);
    this.userInput = '';

    // Simulate AI response
    this.isTyping = true;
    setTimeout(() => {
      const aiMessage: ChatMessage = {
        id: 'ai-' + Date.now(),
        role: 'assistant',
        content: `Thank you for your message: "${userMessage.content}". I'm here to help with your infrastructure needs!`,
        timestamp: new Date()
      };
      session.messages.push(aiMessage);
      this.isTyping = false;
      this.scrollToBottom();
    }, 1500);

    this.scrollToBottom();
  }

  canSend(): boolean {
    return this.userInput.trim().length > 0 && !this.isTyping;
  }

  // Input handling
  handleKeyDown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.sendMessage();
    }
  }

  onInputChange(): void {
    const lines = this.userInput.split('\n').length;
    this.textareaRows = Math.min(Math.max(lines, 1), 5);
  }

  applySuggestion(suggestion: string): void {
    this.userInput = suggestion;
    this.showSuggestions = false;
  }

  // Utility methods
  trackBySessionId(index: number, session: ChatSession): string {
    return session.id;
  }

  formatMessage(content: string): string {
    return content.replace(/\n/g, '<br>');
  }

  getMessageTime(index: number): string {
    const message = this.currentMessages[index];
    if (message && message.timestamp) {
      return message.timestamp.toLocaleTimeString([], { 
        hour: '2-digit', 
        minute: '2-digit' 
      });
    }
    return '';
  }

  getLastMessagePreview(session: ChatSession): string {
    if (session.messages.length === 0) return 'No messages yet';
    const lastMessage = session.messages[session.messages.length - 1];
    return lastMessage.content.length > 50 ? 
      lastMessage.content.substring(0, 50) + '...' : 
      lastMessage.content;
  }

  scrollToBottom(): void {
    if (this.scrollContainer) {
      this.scrollContainer.nativeElement.scrollTop = this.scrollContainer.nativeElement.scrollHeight;
    }
  }

  // Message actions (simple implementations)
  copyMessage(content: string): void {
    this.inputStatus = 'Message copied!';
    setTimeout(() => this.inputStatus = '', 2000);
  }

  regenerateResponse(messageIndex: number): void {
    this.inputStatus = 'Regenerating response...';
    setTimeout(() => this.inputStatus = '', 2000);
  }
}