"""
Unit Tests for Graph and Distributed Systems Solvers in Quiz-Pilot.
"""

import unittest
from quiz_pilot.graph_solvers import (
    ChandyLamportSolver,
    MulticastSimulator,
    LamportVectorClockSolver
)


class TestGraphSolvers(unittest.TestCase):
    def test_chandy_lamport_solver(self):
        solver = ChandyLamportSolver(["P1", "P2"])
        events = [
            {'type': 'send', 'msg': 'm1', 'src': 'P1', 'dst': 'P2'},
            {'type': 'snapshot_init', 'src': 'P1'},
            {'type': 'marker_recv', 'dst': 'P2'},
            {'type': 'recv', 'msg': 'm1', 'src': 'P1', 'dst': 'P2'}
        ]
        res = solver.simulate(events)
        self.assertIn("channel_messages", res)
        self.assertIn("both_in_process_state", res)

    def test_lamport_vector_clock_solver(self):
        solver = LamportVectorClockSolver(num_processes=2)
        solver.add_message('m1', src=0, dst=1)
        solver.add_process_trace(0, [('send', 'm1')])
        solver.add_process_trace(1, [('recv', 'm1')])
        
        res = solver.solve()
        ev0 = res['events']['P0_send_m1']
        ev1 = res['events']['P1_recv_m1']
        
        self.assertEqual(ev0['lamport'], 1)
        self.assertEqual(ev1['lamport'], 2)
        self.assertEqual(ev0['vector'], [1, 0])
        self.assertEqual(ev1['vector'], [1, 1])
        self.assertFalse(solver.is_concurrent('P0_send_m1', 'P1_recv_m1'))

    def test_fifo_multicast_simulator(self):
        sim = MulticastSimulator(num_processes=3)
        multicasts = [{'id': 'M1', 'src': 0}, {'id': 'M2', 'src': 0}]
        # M2 arrives before M1 at receiver 1
        arrivals = [{'msg': 'M2', 'dst': 1}, {'msg': 'M1', 'dst': 1}]
        res = sim.simulate_fifo(3, multicasts, arrivals)
        self.assertEqual(res['total_buffered'], 1)


if __name__ == "__main__":
    unittest.main()
