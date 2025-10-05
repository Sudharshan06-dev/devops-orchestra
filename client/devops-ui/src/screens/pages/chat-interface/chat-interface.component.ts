import { CommonModule } from '@angular/common';
import { Component, ViewChild, ElementRef, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RequestService } from '../../../services/request.service';
import { CHAT_API_ROUTE } from '../../../environment';
import { LocalStorageHelper } from '../../../services/local-storage.service';
import { ToasterHelper } from '../../../services/toast.service';
import { SKIP_SPINNER_TRUE } from '../../../interceptors/spinner.interceptor';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  title?: string;
  chat_id?: string;
  message_id?: string;
}

interface ChatMessagePreview {
  chat_id: string,
  title: string,
  timestamp: Date
}

interface ChatMessageRequest {
  content: string;
  timestamp: Date;
  chat_id?: string;
}

@Component({
  selector: 'app-chat-interface',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './chat-interface.component.html',
  styleUrl: './chat-interface.component.css'
})

export class ChatInterfaceComponent implements OnInit {
  public currentMessages: ChatMessage[] = [];
  public pastChatHistory: ChatMessagePreview[] = [];
  public userInput: string = '';
  public isTyping: boolean = false;
  public textareaRows: number = 1;
  public showSuggestions: boolean = false;
  public inputStatus: string = '';
  public chatId: string = '';
  public userId: number = 0;
  public chatTitle: string = 'New Chat';
  public isOnline: boolean = true;

  public suggestions: string[] = [
    'Analyze my AWS infrastructure',
    'Check ECS service health',
    'Review Terraform configuration',
    'Troubleshoot deployment issues',
    'Monitor application performance',
    'Security audit checklist'
  ];

  public inputSuggestions: string[] = [];

  @ViewChild('scrollContainer') scrollContainer!: ElementRef;
  @ViewChild('messageInput') messageInput!: ElementRef;

  constructor(
    private requestService: RequestService,
    private localStorage: LocalStorageHelper,
    private toasterService: ToasterHelper
  ) {
    this.loadAllChatHistory();
  }

  ngOnInit(): void {
    this.userId = this.localStorage.getItem('user_details')?.user_id;
  }

  loadAllChatHistory(): void {

    this.requestService.get(`${CHAT_API_ROUTE}/all`).subscribe({
      next: (data: ChatMessagePreview[] | any) => {
        this.pastChatHistory = data || [];
      },
      error: (err: any) => {
        this.toasterService.error(err?.error);
      }
    });
  }

  loadChatHistory(chat_id: string | undefined): void {

    if (!chat_id) return;

    this.chatId = chat_id;

    this.requestService.get(`${CHAT_API_ROUTE}/history/?chat_id=${chat_id}`).subscribe({
      next: (data: ChatMessage[] | any) => {
        this.currentMessages = data || [];
        setTimeout(() => this.scrollToBottom(), 0);
      },
      error: (err: any) => {
        this.toasterService.error(err?.error);
      }
    });
  }

  deleteChatHistory(chat_id: string | undefined): void {

    if (!chat_id) {
      this.pastChatHistory.shift()
      return
    }

    this.requestService.get(`${CHAT_API_ROUTE}/delete/chat_id=${chat_id}`).subscribe({
      next: (data: any) => {
        this.toasterService.success(data);
        this.loadAllChatHistory();
        if (this.chatId === chat_id) {
          this.currentMessages = [];
          this.chatId = '';
        }
      },
      error: (err: any) => {
        this.toasterService.error(err?.error);
      }
    });
  }

  async sendMessage() {

    if (!this.canSend()) return;

    const timestamp = new Date();

    const userMessage: ChatMessage = {
      role: 'user',
      content: this.userInput.trim(),
      timestamp,
      title: this.chatTitle,
      chat_id: this.chatId
    };

    this.currentMessages = [...this.currentMessages, userMessage];
    this.isTyping = true;
    this.scrollToBottom();

    const assistantMessage: ChatMessage = {
      role: 'assistant',
      content: '',
      timestamp: new Date()
    };

    this.currentMessages = [...this.currentMessages, assistantMessage];

    const requestPayload: ChatMessageRequest = {
      content: userMessage.content,
      timestamp,
      chat_id: this.chatId || ''
    };

    this.userInput = '';

    try {
      const response = await fetch(`${CHAT_API_ROUTE}/ask`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.requestService.authToken}`
        },
        body: JSON.stringify({
          role: 'user',
          content: userMessage.content,
          timestamp,
          chat_id: this.chatId || ''
        })
      });

      if (!response.body) throw new Error('No response stream');

      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');

      let gotChatId = false;
      let partial = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        partial += chunk;

        // Handle case where multiple chunks may come together
        while (partial.includes('\n')) {
          const [line, rest] = partial.split('\n', 2);
          partial = rest;

          if (!gotChatId && line.startsWith("__CHAT_ID__")) {
            const newChatId = line.split(":")[1]?.trim();
            if (newChatId) {
              this.chatId = newChatId;
              gotChatId = true;
            }
            continue; // Don't render __CHAT_ID__
          }

          assistantMessage.content += line;

          // Re-assign the message to trigger Angular change detection
          this.currentMessages = [...this.currentMessages.slice(0, -1), { ...assistantMessage }];
          this.scrollToBottom();
        }
      }

      // Handle any final remaining chunk (after last \n)
      if (partial && !partial.startsWith("__CHAT_ID__")) {
        assistantMessage.content += partial;
        this.currentMessages = [...this.currentMessages.slice(0, -1), { ...assistantMessage }];
      }

      this.isTyping = false;

    } catch (err: any) {
      console.error('Streaming error', err);
      this.toasterService.error('Streaming error. Please try again.');
      this.isTyping = false;
    }
  }

  startNewChat(): void {
    this.currentMessages = [];
    const newChat: ChatMessagePreview = {
      timestamp: new Date(),
      title: 'New Chat',
      chat_id: ''
    }
    this.pastChatHistory.unshift(newChat)
  }

  canSend(): boolean {
    return this.userInput.trim().length > 0 && !this.isTyping;
  }

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

  scrollToBottom(): void {
    if (this.scrollContainer) {
      setTimeout(() => {
        this.scrollContainer.nativeElement.scrollTop = this.scrollContainer.nativeElement.scrollHeight;
      }, 0);
    }
  }

  formatMessage(content: string): string {
    return content.replace(/\n/g, '<br>');
  }

  getMessageTime(index: number): string {
    const message = this.currentMessages[index];
    return message?.timestamp
      ? new Date(message.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : '';
  }

  copyMessage(content: string): void {
    navigator.clipboard.writeText(content);
    this.inputStatus = 'Message copied!';
    setTimeout(() => (this.inputStatus = ''), 2000);
  }

  regenerateResponse(index: number): void {
    this.inputStatus = 'Regenerating response...';
    this.sendMessage()
  }

  applySuggestion(suggestion: string): void {
    this.userInput = suggestion;
    this.showSuggestions = false;
  }

  getLastMessagePreview(content: string): string {
    if (!content) return 'No messages yet';
    const preview = content.replace(/<[^>]*>/g, '');
    return preview.length > 50 ? preview.substring(0, 50) + '...' : preview;
  }
}