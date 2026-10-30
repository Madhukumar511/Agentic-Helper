"""
Graph and Distributed System Algorithm Solvers for Quiz-Pilot / Agentic-Helper.

Provides automated analytical solvers for:
1. Chandy-Lamport Distributed Snapshot Analysis
2. Multicast FIFO & Causal Ordering Simulation (Vector Clocks & Buffering)
3. Virtual Synchrony State Validator
4. Lamport Timestamps, Vector Timestamps & Event Concurrency Analysis
"""

from typing import List, Dict, Tuple, Set, Optional


class ChandyLamportSolver:
    """
    Simulates Chandy-Lamport distributed snapshot algorithm over discrete events.
    """
    def __init__(self, processes: List[str]):
        self.processes = processes
        self.snapshots_taken: Dict[str, bool] = {p: False for p in processes}
        self.channels_recording: Dict[Tuple[str, str], bool] = {}
        self.channel_states: Dict[Tuple[str, str], List[str]] = {}

    def simulate(self, events: List[Dict]) -> Dict:
        """
        events: list of dicts with:
        {'type': 'send'/'recv'/'marker_send'/'marker_recv', 'msg': str, 'src': str, 'dst': str}
        """
        both_in_process_state = 0
        in_channel_states = []
        both_after_snapshot = 0
        send_after_recv_before = 0
        
        # Track message states
        msg_send_before = {}
        msg_recv_before = {}
        
        for e in events:
            etype = e['type']
            m = e.get('msg')
            src = e.get('src')
            dst = e.get('dst')
            
            if etype == 'snapshot_init':
                self.snapshots_taken[src] = True
            elif etype == 'marker_recv':
                if not self.snapshots_taken[dst]:
                    self.snapshots_taken[dst] = True
            elif etype == 'send':
                msg_send_before[m] = self.snapshots_taken[src] == False
            elif etype == 'recv':
                msg_recv_before[m] = self.snapshots_taken[dst] == False
                
        for m in msg_send_before:
            s_before = msg_send_before[m]
            r_before = msg_recv_before.get(m, False)
            
            if s_before and r_before:
                both_in_process_state += 1
            elif s_before and not r_before:
                in_channel_states.append(m)
            elif not s_before and not r_before:
                both_after_snapshot += 1
            elif not s_before and r_before:
                send_after_recv_before += 1

        in_channel_states.sort()
        return {
            "channel_messages": in_channel_states,
            "both_in_process_state": both_in_process_state,
            "both_after_snapshot": both_after_snapshot,
            "send_after_recv_before": send_after_recv_before
        }


class MulticastSimulator:
    """
    Simulates FIFO and Causal Multicast delivery with Vector Clocks.
    Tracks exact sequence vectors and buffered message counts.
    """
    def __init__(self, num_processes: int = 4):
        self.N = num_processes
        
    def simulate_causal(self, num_processes: int, multicasts: List[Dict], arrivals: List[Dict]) -> Dict:
        """
        multicasts: [{'id': 'M1', 'src': 1}, ...]
        arrivals: ordered list of arrivals: [{'msg': 'M1', 'dst': 0}, ...]
        """
        vector_clocks = {p: [0] * num_processes for p in range(num_processes)}
        buffers = {p: [] for p in range(num_processes)}
        buffered_count = 0
        
        # Map message metadata
        msg_timestamps = {}
        for m in multicasts:
            src = m['src']
            vector_clocks[src][src] += 1
            msg_timestamps[m['id']] = (src, list(vector_clocks[src]))

        # Simulate arrivals
        for arr in arrivals:
            dst = arr['dst']
            mid = arr['msg']
            src, v_m = msg_timestamps[mid]
            
            # Check delivery condition
            # 1. v_m[src] == V_dst[src] + 1
            # 2. for k != src: v_m[k] <= V_dst[k]
            can_deliver = (v_m[src] == vector_clocks[dst][src] + 1) and all(
                v_m[k] <= vector_clocks[dst][k] for k in range(num_processes) if k != src
            )
            
            if can_deliver:
                vector_clocks[dst][src] += 1
                # Try flush buffer
                flushed = True
                while flushed:
                    flushed = False
                    for b_mid, b_src, b_vm in list(buffers[dst]):
                        if (b_vm[b_src] == vector_clocks[dst][b_src] + 1) and all(
                            b_vm[k] <= vector_clocks[dst][k] for k in range(num_processes) if k != b_src
                        ):
                            vector_clocks[dst][b_src] += 1
                            buffers[dst].remove((b_mid, b_src, b_vm))
                            flushed = True
                            break
            else:
                buffers[dst].append((mid, src, v_m))
                buffered_count += 1
                
        return {
            "final_vectors": {p: ",".join(map(str, vector_clocks[p])) for p in range(num_processes)},
            "total_buffered": buffered_count
        }

    def simulate_fifo(self, num_processes: int, multicasts: List[Dict], arrivals: List[Dict]) -> Dict:
        """
        FIFO multicast delivery: messages from same sender must be sequential.
        """
        delivered = {p: [0] * num_processes for p in range(num_processes)}
        buffers = {p: [] for p in range(num_processes)}
        buffered_count = 0
        
        msg_seq = {}
        sender_counts = {p: 0 for p in range(num_processes)}
        for m in multicasts:
            src = m['src']
            sender_counts[src] += 1
            msg_seq[m['id']] = (src, sender_counts[src])
            
        for arr in arrivals:
            dst = arr['dst']
            mid = arr['msg']
            src, seq = msg_seq[mid]
            
            if seq == delivered[dst][src] + 1:
                delivered[dst][src] += 1
                flushed = True
                while flushed:
                    flushed = False
                    for b_mid, b_src, b_seq in list(buffers[dst]):
                        if b_seq == delivered[dst][b_src] + 1:
                            delivered[dst][b_src] += 1
                            buffers[dst].remove((b_mid, b_src, b_seq))
                            flushed = True
                            break
            else:
                buffers[dst].append((mid, src, seq))
                buffered_count += 1

        return {
            "final_vectors": {p: ",".join(map(str, delivered[p])) for p in range(num_processes)},
            "total_buffered": buffered_count
        }


class LamportVectorClockSolver:
    """
    Computes Lamport Timestamps, Vector Clocks, and Concurrency for Distributed Executions.
    """
    def __init__(self, num_processes: int):
        self.num_processes = num_processes
        self.events: Dict[str, Dict] = {}
        self.proc_events: Dict[int, List[str]] = {p: [] for p in range(num_processes)}
        self.adj: Dict[str, Set[str]] = {}
        self.in_degree: Dict[str, int] = {}
        self.messages: Dict[str, Dict] = {}

    def add_message(self, msg_id: str, src: int, dst: int):
        self.messages[msg_id] = {'src': src, 'dst': dst}

    def add_process_trace(self, proc: int, trace: List[Tuple[str, str]]):
        """
        trace: list of (event_type ('send'|'recv'|'internal'), msg_id)
        """
        for etype, mname in trace:
            ename = f"P{proc}_{etype}_{mname}"
            self.events[ename] = {
                'name': ename,
                'proc': proc,
                'type': etype,
                'msg': mname,
                'lamport': 0,
                'vector': [0] * self.num_processes
            }
            self.proc_events[proc].append(ename)
            self.adj[ename] = set()
            self.in_degree[ename] = 0

    def solve(self):
        # 1. Add process sequential edges
        for proc in range(self.num_processes):
            pevs = self.proc_events[proc]
            for i in range(len(pevs) - 1):
                u, v = pevs[i], pevs[i+1]
                if v not in self.adj[u]:
                    self.adj[u].add(v)
                    self.in_degree[v] += 1

        # 2. Add message transmission edges
        send_events = {ev['msg']: ev['name'] for ev in self.events.values() if ev['type'] == 'send'}
        recv_events = {ev['msg']: ev['name'] for ev in self.events.values() if ev['type'] == 'recv'}
        for mid in send_events:
            if mid in recv_events:
                u, v = send_events[mid], recv_events[mid]
                if v not in self.adj[u]:
                    self.adj[u].add(v)
                    self.in_degree[v] += 1

        # 3. Topological sort
        queue = [ename for ename, deg in self.in_degree.items() if deg == 0]
        topo_order = []
        while queue:
            u = queue.pop(0)
            topo_order.append(u)
            for v in self.adj[u]:
                self.in_degree[v] -= 1
                if self.in_degree[v] == 0:
                    queue.append(v)

        # 4. Compute Lamport Timestamps
        l_clock = {p: 0 for p in range(self.num_processes)}
        msg_l = {}
        for ename in topo_order:
            ev = self.events[ename]
            p = ev['proc']
            if ev['type'] == 'send':
                l_clock[p] += 1
                ev['lamport'] = l_clock[p]
                msg_l[ev['msg']] = ev['lamport']
            elif ev['type'] == 'recv':
                ev['lamport'] = max(l_clock[p], msg_l.get(ev['msg'], 0)) + 1
                l_clock[p] = ev['lamport']
            else:
                l_clock[p] += 1
                ev['lamport'] = l_clock[p]

        # 5. Compute Vector Timestamps
        v_clock = {p: [0] * self.num_processes for p in range(self.num_processes)}
        msg_v = {}
        for ename in topo_order:
            ev = self.events[ename]
            p = ev['proc']
            v_clock[p][p] += 1
            if ev['type'] == 'send':
                ev['vector'] = list(v_clock[p])
                msg_v[ev['msg']] = list(ev['vector'])
            elif ev['type'] == 'recv':
                m_vec = msg_v.get(ev['msg'], [0] * self.num_processes)
                for k in range(self.num_processes):
                    if k != p:
                        v_clock[p][k] = max(v_clock[p][k], m_vec[k])
                ev['vector'] = list(v_clock[p])
            else:
                ev['vector'] = list(v_clock[p])

        # 6. Compute transitive closure for reachability & concurrency
        self.reachable = {ename: set() for ename in self.events}
        for u in reversed(topo_order):
            self.reachable[u].add(u)
            for v in self.adj[u]:
                self.reachable[u].update(self.reachable[v])

        return {
            'events': self.events,
            'topo_order': topo_order
        }

    def is_concurrent(self, event_a: str, event_b: str) -> bool:
        a_leads_to_b = event_b in self.reachable.get(event_a, set())
        b_leads_to_a = event_a in self.reachable.get(event_b, set())
        return not a_leads_to_b and not b_leads_to_a

    def get_concurrent_events(self, target_event: str) -> List[str]:
        return [
            ename for ename in self.events
            if ename != target_event and self.is_concurrent(target_event, ename)
        ]
