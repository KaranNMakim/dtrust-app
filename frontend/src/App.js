import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Show } from "@clerk/react";
import ClerkAuthProvider from "@/components/auth/ClerkAuthProvider";
import { AuthedShell } from "@/components/app-shell";
import { SignInPage, SignUpPage } from "@/pages/Auth";
import Home from "@/pages/Home";
import Ask from "@/pages/Ask";
import Reconcile from "@/pages/Reconcile";
import Metrics from "@/pages/Metrics";
import MetricDetail from "@/pages/MetricDetail";
import Conflicts from "@/pages/Conflicts";
import Recommendations from "@/pages/Recommendations";
import Graph from "@/pages/Graph";
import Calibration from "@/pages/Calibration";
import Ingest from "@/pages/Ingest";
import Billing from "@/pages/Billing";

function Protected() {
  return (
    <>
      <Show when="signed-in"><AuthedShell /></Show>
      <Show when="signed-out"><Navigate to="/sign-in" replace /></Show>
    </>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ClerkAuthProvider>
        <Routes>
          <Route path="/sign-in/*" element={<SignInPage />} />
          <Route path="/sign-up/*" element={<SignUpPage />} />
          <Route element={<Protected />}>
            <Route path="/" element={<Home />} />
            <Route path="/ask" element={<Ask />} />
            <Route path="/reconcile" element={<Reconcile />} />
            <Route path="/metrics" element={<Metrics />} />
            <Route path="/metrics/:id" element={<MetricDetail />} />
            <Route path="/conflicts" element={<Conflicts />} />
            <Route path="/recommendations" element={<Recommendations />} />
            <Route path="/graph" element={<Graph />} />
            <Route path="/calibration" element={<Calibration />} />
            <Route path="/ingest" element={<Ingest />} />
            <Route path="/billing" element={<Billing />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </ClerkAuthProvider>
    </BrowserRouter>
  );
}
