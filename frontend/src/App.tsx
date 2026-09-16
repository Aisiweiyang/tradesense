import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { Loading } from "./components/ui";

// 页面按路由分割：首屏只拉当前页的 chunk，其余按需加载
const Layout = lazy(() => import("./Layout"));
const Login = lazy(() => import("./pages/Login"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Today = lazy(() => import("./pages/Today"));
const Inquiries = lazy(() => import("./pages/Inquiries"));
const InquiryNew = lazy(() => import("./pages/InquiryNew"));
const InquiryDetail = lazy(() => import("./pages/InquiryDetail"));
const Customers = lazy(() => import("./pages/Customers"));
const Products = lazy(() => import("./pages/Products"));
const ProductImport = lazy(() => import("./pages/ProductImport"));
const Suppliers = lazy(() => import("./pages/Suppliers"));
const Quotes = lazy(() => import("./pages/Quotes"));
const Followups = lazy(() => import("./pages/Followups"));
const Connectors = lazy(() => import("./pages/Connectors"));
const SyncLogs = lazy(() => import("./pages/SyncLogs"));
const ShipmentWorkbench = lazy(() => import("./pages/ShipmentWorkbench"));
const Settings = lazy(() => import("./pages/Settings"));
const Audit = lazy(() => import("./pages/Audit"));
const Analytics = lazy(() => import("./pages/Analytics"));
const Glossary = lazy(() => import("./pages/Glossary"));
const Knowledge = lazy(() => import("./pages/Knowledge"));

export default function App() {
  return (
    <Suspense fallback={<Loading />}>
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
          <Route path="/knowledge" element={<Knowledge />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </Suspense>
  );
}
