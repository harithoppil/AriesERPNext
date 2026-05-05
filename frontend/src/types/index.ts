export interface User {
  id: string; name: string; email: string; avatar: string; role: string;
}

export interface Enquiry {
  id: string; client: string; contactName: string; email: string; phone: string;
  service: string; value: number; currency: string; status: 'new' | 'qualified' | 'proposal' | 'negotiation' | 'approved' | 'rejected';
  assignedTo: string; date: string; description: string; notes: string[];
}

export interface Personnel {
  id: string; name: string; role: string; department: string; email: string;
  phone: string; location: string; avatar: string;
  certifications: { name: string; status: 'valid' | 'expiring' | 'expired'; expiryDate?: string; level?: string }[];
}

export interface Asset {
  id: string; name: string; category: 'ROV' | 'NDT' | 'Crane' | 'Diving' | 'Survey' | 'Communication';
  serialNumber: string; location: string; lastCalibration: string; nextCalibration: string;
  status: 'calibrated' | 'due-soon' | 'overdue';
}

export interface Project {
  id: string; name: string; client: string; description: string;
  progress: number; budgetSpent: number; budgetTotal: number;
  startDate: string; endDate: string; location: string; team: number;
  status: 'active' | 'planning' | 'completed' | 'on-hold';
}

export interface StockItem {
  id: string; sku: string; name: string; category: string;
  quantity: number; warehouse: 'Jebel Ali' | 'Mussafah' | 'Das Island';
  reorderLevel: number; unitCost: number;
  status: 'adequate' | 'low' | 'critical';
}

export interface Invoice {
  id: string; number: string; client: string; issueDate: string; dueDate: string;
  subtotal: number; vat: number; total: number; status: 'paid' | 'pending' | 'overdue' | 'draft';
}

export interface Payment {
  id: string; number: string; date: string; client: string;
  amount: number; method: 'bank' | 'cash' | 'cheque'; reference: string;
  status: 'cleared' | 'pending';
}

export interface Supplier {
  id: string; name: string; category: string; email: string; phone: string;
  address: string; rating: number; paymentTerms: string;
}

export interface PurchaseOrder {
  id: string; number: string; supplier: string; date: string; deliveryDate: string;
  items: number; total: number; status: 'pending' | 'approved' | 'received';
}

export interface Workflow {
  id: string; name: string; description: string; nodes: number; runs: number;
  status: 'active' | 'paused';
}

export interface Persona {
  id: string; name: string; description: string; tools: string[]; tone: string;
  systemPrompt: string;
}

export interface Channel {
  id: string; name: string; type: string; description: string;
  status: 'connected' | 'disconnected' | 'error';
  lastSync: string; messagesToday: number;
}

export interface WikiPage {
  id: string; title: string; category: string; author: string;
  lastEdited: string; content: string; tags: string[];
}

export interface ChatMessage {
  id: string; sender: 'user' | 'ai'; content: string; timestamp: string;
}

export interface DashboardMetric {
  label: string; value: string | number; change: number; changeType: 'increase' | 'decrease';
  icon: string; prefix?: string; suffix?: string;
}

export interface DynamicUI {
  id: string; type: 'dashboard' | 'form' | 'kanban' | 'report';
  title: string; description: string; config: Record<string, unknown>;
}

export interface RagDocument {
  id: string; name: string; type: 'pdf' | 'doc' | 'txt';
  size: string; status: 'indexed' | 'pending' | 'failed'; indexedAt?: string;
}

export interface Notification {
  id: string; message: string; time: string; read: boolean; type: 'info' | 'warning' | 'success' | 'error';
}
