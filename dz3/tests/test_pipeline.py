import pathlib,sys,unittest,collections
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'src'))
from pipeline import selected,skills,map_chunk

class PipelineTests(unittest.TestCase):
    def test_filter_boundaries(self):
        for name in ['Senior DevOps Engineer','Dev-Ops инженер','девопс-инженер']:
            self.assertTrue(selected({'name':name,'role':''}))
        self.assertFalse(selected({'name':'Разработчик Docker','role':'Программист, разработчик'}))
        self.assertFalse(selected({'name':'MyDevOpsTool developer','role':''}))
        self.assertTrue(selected({'name':'SRE','role':'DevOps-инженер'}))
        self.assertFalse(selected({'name':'SRE','role':'Системный инженер'}))

    def test_normalization_and_exact_combinations(self):
        sk=skills(' Linux ; Docker;LINUX; ; Git\t')
        self.assertEqual(sk,['docker','git','linux'])
        _,counts=map_chunk((0,[sk],30,False,False))
        self.assertEqual(counts[0],collections.Counter({('docker',):1,('git',):1,('linux',):1}))
        self.assertEqual(counts[1],collections.Counter({('docker','git'):1,('docker','linux'):1,('git','linux'):1}))
        self.assertEqual(counts[2],collections.Counter({('docker','git','linux'):1}))

    def test_empty_and_optimized_equivalence(self):
        stacks=[[],['a'],['a','b'],['a','b','c','d']]
        self.assertEqual(map_chunk((1,stacks,3,False,False)),map_chunk((1,stacks,3,True,False)))
        self.assertEqual(map_chunk((2,[[]],30,False,False))[1],[collections.Counter() for _ in range(3)])

if __name__=='__main__':unittest.main()
