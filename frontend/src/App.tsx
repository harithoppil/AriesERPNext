import { HashRouter, Routes, Route } from 'react-router-dom';
import AppShell from './components/layout/AppShell';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import EnquiriesList from './pages/EnquiriesList';
import EnquiryDetail from './pages/EnquiryDetail';
import Personnel from './pages/Personnel';
import Assets from './pages/Assets';
import Projects from './pages/Projects';
import Stock from './pages/Stock';
import PurchaseOrders from './pages/PurchaseOrders';
import Invoices from './pages/Invoices';
import Payments from './pages/Payments';
import Suppliers from './pages/Suppliers';
import Wiki from './pages/Wiki';
import WikiEdit from './pages/WikiEdit';
import WorkflowBuilder from './pages/WorkflowBuilder';
import PersonaManager from './pages/PersonaManager';
import ChannelHub from './pages/ChannelHub';
import RagAdmin from './pages/RagAdmin';
import DynamicRenderer from './pages/DynamicRenderer';
import LetterheadGenerator from './pages/LetterheadGenerator';

export default function App() {
  return (
    <HashRouter>
      <Routes>
        <Route path="/" element={<Login />} />
        <Route element={<AppShell />}>
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/enquiries" element={<EnquiriesList />} />
          <Route path="/enquiries/:id" element={<EnquiryDetail />} />
          <Route path="/personnel" element={<Personnel />} />
          <Route path="/assets" element={<Assets />} />
          <Route path="/projects" element={<Projects />} />
          <Route path="/stock" element={<Stock />} />
          <Route path="/purchase-orders" element={<PurchaseOrders />} />
          <Route path="/invoices" element={<Invoices />} />
          <Route path="/payments" element={<Payments />} />
          <Route path="/suppliers" element={<Suppliers />} />
          <Route path="/wiki" element={<Wiki />} />
          <Route path="/wiki/edit/:id" element={<WikiEdit />} />
          <Route path="/settings/workflows" element={<WorkflowBuilder />} />
          <Route path="/settings/personas" element={<PersonaManager />} />
          <Route path="/settings/channels" element={<ChannelHub />} />
          <Route path="/settings/rag" element={<RagAdmin />} />
          <Route path="/dynamic/:id" element={<DynamicRenderer />} />
          <Route path="/tools/letterhead" element={<LetterheadGenerator />} />
        </Route>
      </Routes>
    </HashRouter>
  );
}
