import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { 
  Zap, Mic, Settings, Trash2, AlertTriangle, FileText, CheckCircle2,
  Cpu, Server, Send, Loader, Plus, Eye
} from 'lucide-react';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
  actions?: { label: string; action: string }[];
}

export function AgentChatPage() {
  const { t } = useTranslation();
  
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: '1',
      role: 'assistant',
      content: 'مرحباً! أنا NexusAI Pro - مساعدك الهندسي الذكي. يمكنني مساعدتك في فحوصات الامتثال، حسابات الأحمال، تحليل الأعطال، وأكثر بكثير. كيف يمكنني مساعدتك اليوم؟',
      timestamp: new Date(),
    }
  ]);
  
  const [inputValue, setInputValue] = useState('');
  const [isListening, setIsListening] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  
  const quickCommands = [
    'فحص الامتثال',
    'حساب الحمل',
    'دراسة القوس الكهربائي',
    'تحديد حجم الكابل',
    'تحليل التيار القصير',
    'دراسة التنسيق',
    'إنشاء مخطط',
    'تصدير التقرير'
  ];
  
  useEffect(() => {
    if (scrollAreaRef.current) {
      scrollAreaRef.current.scrollTop = scrollAreaRef.current.scrollHeight;
    }
  }, [messages]);
  
  const handleSendMessage = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!inputValue.trim()) return;
    
    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: 'user',
      content: inputValue,
      timestamp: new Date(),
    };
    
    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);
    
    try {
      // Simulate API call delay
      await new Promise(resolve => setTimeout(resolve, 1000));
      
      const assistantMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'شكراً على سؤالك! أنا أقوم بمعالجة طلبك الآن. في بيئة الإنتاج، سأتصل بـ GraphRAG API للحصول على إجابة ذكية مستندة إلى قاعدة المعرفة الخاصة بنظام الحرائق.',
        timestamp: new Date(),
        actions: [
          { label: 'عرض التفاصيل', action: 'details' },
          { label: 'تصدير', action: 'export' }
        ]
      };
      
      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      console.log('[v0] Error:', error);
      
      // Fallback response
      const fallbackMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: 'عذراً، حدث خطأ في معالجة الطلب. يرجى المحاولة مرة أخرى.',
        timestamp: new Date(),
      };
      
      setMessages(prev => [...prev, fallbackMessage]);
    } finally {
      setIsLoading(false);
    }
  };
  
  const handleQuickCommand = (command: string) => {
    setInputValue(command);
  };
  
  const handleClearHistory = () => {
    setMessages([{
      id: '1',
      role: 'assistant',
      content: 'تم مسح السجل. كيف يمكنني مساعدتك؟',
      timestamp: new Date(),
    }]);
  };
  
  return (
    <div className="h-screen flex flex-col bg-background text-foreground">
      {/* Header */}
      <div className="h-16 border-b border-border flex items-center justify-between px-6 bg-card">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-secondary to-secondary/60 flex items-center justify-center border border-secondary/50">
            <Zap className="h-5 w-5 text-secondary-foreground" />
          </div>
          <div>
            <h1 className="font-semibold text-base text-foreground">NexusAI Pro</h1>
            <p className="text-xs text-muted-foreground">مساعد هندسي ذكي</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="icon"
            className="h-9 w-9 border-border hover:bg-muted"
            onClick={handleClearHistory}
          >
            <Trash2 className="h-4 w-4" />
          </Button>
          <Button
            variant="outline"
            size="icon"
            className="h-9 w-9 border-border hover:bg-muted"
          >
            <Settings className="h-4 w-4" />
          </Button>
        </div>
      </div>
      
      {/* Chat Area */}
      <ScrollArea className="flex-1 p-6">
        <div className="max-w-3xl mx-auto space-y-6">
          {messages.map((message) => (
            <div key={message.id} className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {message.role === 'assistant' && (
                <div className="w-8 h-8 rounded bg-secondary/20 flex items-center justify-center border border-secondary/50 shrink-0 mr-3">
                  <Zap className="h-4 w-4 text-secondary" />
                </div>
              )}
              
              <div className={`max-w-md ${message.role === 'user' ? 'order-2 ml-3' : ''}`}>
                <div className={`px-4 py-3 rounded-xl ${
                  message.role === 'user'
                    ? 'bg-secondary/20 text-foreground border border-secondary/30 rounded-br-none'
                    : 'bg-muted text-foreground border border-border rounded-bl-none'
                }`}>
                  <p className="text-sm leading-relaxed">{message.content}</p>
                </div>
                
                {message.actions && message.role === 'assistant' && (
                  <div className="flex gap-2 mt-3 flex-wrap">
                    {message.actions.map((action, idx) => (
                      <Button
                        key={idx}
                        variant="outline"
                        size="sm"
                        className="h-8 text-xs bg-transparent border-border hover:bg-muted"
                      >
                        {action.action === 'details' ? <Eye className="w-3 h-3 mr-1" /> : <FileText className="w-3 h-3 mr-1" />}
                        {action.label}
                      </Button>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          
          {isLoading && (
            <div className="flex justify-start">
              <div className="w-8 h-8 rounded bg-secondary/20 flex items-center justify-center border border-secondary/50 shrink-0 mr-3">
                <Loader className="h-4 w-4 text-secondary animate-spin" />
              </div>
              <div className="bg-muted text-foreground border border-border px-4 py-3 rounded-xl rounded-bl-none">
                <p className="text-sm">جاري المعالجة...</p>
              </div>
            </div>
          )}
        </div>
      </ScrollArea>
      
      {/* Quick Commands */}
      <div className="px-6 py-4 border-t border-border bg-card/50">
        <p className="text-xs text-muted-foreground mb-3 font-medium">الأوامر السريعة:</p>
        <div className="flex flex-wrap gap-2">
          {quickCommands.map((cmd) => (
            <Badge
              key={cmd}
              variant="outline"
              className="bg-muted border-border hover:bg-secondary/20 hover:text-secondary hover:border-secondary/50 cursor-pointer py-1.5 px-3"
              onClick={() => handleQuickCommand(cmd)}
            >
              {cmd}
            </Badge>
          ))}
        </div>
      </div>
      
      {/* Input Area */}
      <div className="border-t border-border p-4 bg-card">
        <form onSubmit={handleSendMessage} className="max-w-3xl mx-auto">
          <div className="relative flex items-center gap-2">
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="h-10 w-10 text-muted-foreground hover:text-foreground"
            >
              <Plus className="h-4 w-4" />
            </Button>
            
            <Input
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="اكتب سؤالاً أو أمراً..."
              className="bg-muted border-border flex-1 h-10 rounded-full px-4"
              disabled={isLoading}
            />
            
            <Button
              type="button"
              size="icon"
              variant="ghost"
              className="h-10 w-10 text-muted-foreground hover:text-foreground"
              onClick={() => setIsListening(!isListening)}
            >
              <Mic className={`h-4 w-4 ${isListening ? 'text-secondary' : ''}`} />
            </Button>
            
            <Button
              type="submit"
              size="icon"
              className="h-10 w-10 bg-secondary hover:bg-secondary/90 text-secondary-foreground rounded-full"
              disabled={isLoading || !inputValue.trim()}
            >
              <Send className="h-4 w-4" />
            </Button>
          </div>
        </form>
      </div>
      
      {/* Status Bar */}
      <div className="h-8 bg-background border-t border-border flex items-center justify-between px-6 text-[10px] font-mono text-muted-foreground">
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-1"><Cpu className="w-3 h-3" /> Expert Mode</span>
          <span className="flex items-center gap-1"><Server className="w-3 h-3" /> Current Project</span>
        </div>
        <div className="flex items-center gap-1 text-emerald-500">
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-500"></div> Connected
        </div>
      </div>
    </div>
  );
}
