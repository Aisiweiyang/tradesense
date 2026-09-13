import { useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Layout from "./Layout";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Today from "./pages/Today";
import Inquiries from "./pages/Inquiries";
import InquiryNew from "./pages/InquiryNew";
import InquiryDetail from "./pages/InquiryDetail";
import Customers from "./pages/Customers";
import Products from "./pages/Products";
import ProductImport from "./pages/ProductImport";
import Suppliers from "./pages/Suppliers";
import Quotes from "./pages/Quotes";
import Followups from "./pages/Followups";
import Connectors from "./pages/Connectors";
import SyncLogs from "./pages/SyncLogs";
import ShipmentWorkbench from "./pages/ShipmentWorkbench";
import Settings from "./pages/Settings";
import Audit from "./pages/Audit";
import Analytics from "./pages/Analytics";
import Glossary from "./pages/Glossary";

export default function App() {
  const [ready] = useState(true);
  if (!ready) return null;
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/today" element={<Today />} />
        <Route path="/shipments" element={<ShipmentWorkbench />} />
        <Route path="/shipments/:id" element={<ShipmentWorkbench />} />
        <Route path="/inquiries" element={<Inquiries />} />
        <Route path="/inquiries/new" element={<InquiryNew />} />
        <Route path="/inquiries/:id" element={<InquiryDetail />} />
        <Route path="/customers" element={<Customers />} />
        <Route path="/products" element={<Products />} />
        <Route path="/products/import" element={<ProductImport />} />
        <Route path="/suppliers" element={<Suppliers />} />
        <Route path="/quotes" element={<Quotes />} />
        <Route path="/followups" element={<Followups />} />
        <Route path="/connectors" element={<Connectors />} />
        <Route path="/sync-logs" element={<SyncLogs />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/audit" element={<Audit />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/glossary" element={<Glossary />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
