
import numpy as np
from scipy.stats import ranksums

from tools import Beta,Multi,Table

# Suppress Warnings
import warnings
warnings.simplefilter("ignore")

# Arguments and config parsing
from config import get_config

def get_args():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("mode",nargs="?",default="compare",choices=["compare","fit_beta","query"])
    parser.add_argument("-m","--manifest",default=None,
                        help="TSV file with list of samples (first column) and group labels (second column).")  
    parser.add_argument("-p","--ps_table",default=None,
                        help="Filename and path for .ps.tsv file, output from MESA.")
    parser.add_argument("-s","--sig_file",default=None,
                        help="Filename and path for .sig.tsv file, previously output from splicedice.")
    parser.add_argument("-a","--annotation",default=None,
                        help="GTF or splice_annotation.tsv file with gene annotation (optional for labeling/filtering)")
    parser.add_argument("-o","--output_prefix",
                        help = "Path and file prefix for the output file. '.sig.tsv' or '.match.tsv' will be appended to prefix.")
    parser.add_argument("-c","--config_file",default=None,
                        help = "Optional. For adjusting parameters of splicing analysis.")
    parser.add_argument("-ctrl","--control_name",default=None,
                        help="Sample group label that represents control for comparative analysis (default is first group in manifest).")
    parser.add_argument("-n","--n_threads",default=1,
                        help="Maximum number of processes to use at the same time.")
    return parser.parse_args()
     
def check_args_and_config(args,config):
    if args.mode == "compare":
        if not args.ps_table or not args.manifest:
            exit()
    elif args.mode == "fit_beta":
        return True
    elif args.mode == "compare":
        return True
    return True

#### Main ####
def main():
    # Arguments and configuration specifications
    args = get_args()
    config = get_config(args.config_file)
    check_args_and_config(args=args,config=config)

    if args.manifest:
        manifest = Manifest(filename=args.manifest)
    else:
        manifest = Manifest()

    if args.ps_table:
        ps_table = Table(filename=args.ps_table,store=None)

    if args.mode == "compare":
        groups,med_stats,compare_stats = manifest.compare(ps_table)
        manifest.write_sig(args.output_prefix,groups,med_stats,compare_stats)


    elif args.mode == "fit_beta":
        if args.sig_file:
            groups,compare_stats = manifest.read_sig(args.sig_file,get="compare")
            beta_stats = manifest.fit_betas(ps_table,compare_stats)
        else:
            groups,med_stats,compare_stats = manifest.compare(ps_table,threshold=0.05)
            beta_stats = manifest.fit_betas(ps_table,compare_stats)
        manifest.write_sig(args.output_prefix,groups=groups,beta_stats=beta_stats)

    elif args.mode == "query":
        print("Reading...")
        groups,beta_stats = manifest.read_sig(args.sig_file,get="beta")
        print("Querying...")
        samples,queries,pvals = manifest.query(ps_table,groups,beta_stats)
        print("Writing...")

        manifest.write_pvals(args.output_prefix,samples,queries,pvals)

#### Manifest Class ####    
class Manifest:
    def __init__(self,filename=None,control_name=None):
        self.samples = []
        self.groups = {}
        self.get_group = {}
        self.beta = Beta()
        self.controls = {}
        if filename:
            with open(filename) as manifest_file:
                for line in manifest_file:
                    row = line.rstrip().split("\t")
                    sample_name,group_name = row[0:2]
                    self.samples.append(sample_name)
                    self.get_group[sample_name] = group_name
                    if group_name not in self.groups:
                        if not control_name:
                            control_name = group_name
                        self.groups[group_name] = []
                    self.groups[group_name].append(sample_name)
            for group_name in self.groups.keys():
                self.controls[group_name] = control_name
            self.index = {sample:i for i,sample in enumerate(self.samples)}

    def get_group_indices(self,samples):
        group_indices = {k:[] for k in self.groups.keys()}
        for i,s in enumerate(samples):
            if s in self.get_group:
                group_indices[self.get_group[s]].append(i)
        return {k:v for k,v in group_indices.items() if len(v) > 0}
    
    def read_sig(self,sig_file,get="all"):
        med_stats = {}
        compare_stats = {}
        beta_stats = {}
        with open(sig_file) as tsv:
            columns = tsv.readline().rstrip().split("\t")[1:]
            index = []
            groups = {}
            offset = {}
            for i,column in enumerate(columns):
                info_type,group_name = column.split("_",1)
                if group_name not in groups:
                    groups[group_name] = {}
                groups[group_name][info_type] = i
            for line in tsv:
                row = line.rstrip().split('\t')
                interval = row[0]

                if get == "all":
                    med_stats[interval] = []
                if get == "compare" or get == "all":
                    compare_stats[interval] = []
                if get == "beta" or get == "all":
                    beta_stats[interval] = []

                row = row[1:]
                for i,x in enumerate(row):
                    try:
                        row[i] = float(x)
                    except ValueError:
                        row[i] = float('nan')
                for group_name in groups:
                    if get == "all":
                        median = row[groups[group_name]["median"]]
                        mean = row[groups[group_name]["mean"]]
                        med_stats[interval].append([median,mean])
                    if get == "compare" or get == "all":
                        delta = row[groups[group_name]["delta"]]
                        pval = row[groups[group_name]["pval"]]
                        compare_stats[interval].append([delta,pval])
                    if get == "beta" or get == "all":
                        median = row[groups[group_name]["median"]]
                        alpha = row[groups[group_name]["alpha"]]
                        beta = row[groups[group_name]["beta"]]
                        beta_stats[interval].append([median,alpha,beta])
            
        groups = list(groups.keys())
        if get == "all":
            return groups,med_stats,compare_stats,beta_stats
        elif get == "compare":
            return groups,med_stats,compare_stats
        elif get == "beta":
            return groups,beta_stats
        
    def write_sig(self,output_prefix,groups=None,med_stats=None,compare_stats=None,beta_stats=None,):
        header = ["splice_interval"]
        stats = {}
        for which_stat in [med_stats,compare_stats,beta_stats]:
            if which_stat:
                for interval,values in which_stat.items():
                    if interval not in stats:
                        stats[interval] = []
                    for v in values:
                        stats[interval].extend(v)
                intervals = which_stat.keys()
        for name in groups:
            if med_stats:
                header.extend([f"median_{name}",f"mean_{name}"])
            if compare_stats:
                header.extend([f"delta_{name}",f"pval_{name}"])
            if beta_stats:
                header.extend([f"median_{name}",f"alpha_{name}",f"beta_{name}"])
        with open(f"{output_prefix}.sig.tsv",'w') as tsv:
            tab = '\t'
            tsv.write(f"{tab.join(header)}\n")
            for interval in intervals:
                tsv.write(f"{interval}\t{tab.join(str(x) for x in stats[interval])}\n")

    def write_pvals(self,output_prefix,samples,queries,pvals):
        print("**samples**",samples)
        with open(f"{output_prefix}.pvals.tsv",'w') as tsv:
            tab = "\t"
            tsv.write(f"query\t{tab.join(samples)}\n")
            for i in range(len(queries)):
                for j in range(len(queries)):
                    if i != j:
                        tsv.write(f"{queries[i][j]}\t{tab.join(str(x) for x in pvals[i][j])}\n")

    def compare(self,ps_table,threshold=1):
        med_stats = {}
        compare_stats = {}
        group_indices = self.get_group_indices(ps_table.get_samples())
        for interval,row in ps_table.get_rows():
            nan_check = [np.isnan(x) for x in row]
            values_by_group = {g_name:[row[i] for i in index if not nan_check[i]] for g_name,index in group_indices.items()}
            medians = {g:np.median(values) for g,values in values_by_group.items()}
            stats = [] 
            to_add = False
            for group_name,group_values in values_by_group.items():
                control_name = self.controls[group_name]
                if control_name:
                    delta = medians[group_name] - medians[control_name]
                    if len(group_values)>2 and len(values_by_group[control_name])>2:
                        D,pval = ranksums(group_values, values_by_group[control_name])
                        if pval < threshold:
                            to_add = True
                    else:
                        pval = None
                else:
                    delta,pval = None,None
                stats.append([delta,pval])
            if to_add:
                compare_stats[interval] = stats
                med_stats[interval] = [[medians[group_name],np.mean(group_values)] for group_name,group_values in values_by_group.items()]
        return list(group_indices.keys()),med_stats,compare_stats
    
    def significant_intervals(self,compare_stats,threshold=0.05):
        significant = set()
        for interval,data in compare_stats.items():
            for d in data:
                if d[1] and d[1] < threshold:
                    significant.add(interval)
                    break
        return significant
    
    def row_fit_beta(self,row,group_indices):
        interval,row = row
        nan_check = [np.isnan(x) for x in row]
        mab_row = []
        for index in group_indices.values():
            mab_row.append(self.beta.fit_beta([row[i] for i in index if not nan_check[i]]))
        return interval,mab_row

    def fit_betas(self,ps_table,compare_stats):
        interval_set = self.significant_intervals(compare_stats)
        group_indices = self.get_group_indices(ps_table.get_samples())
        beta_stats = {}
        import multiprocessing
        n = 8
        buffer_ratio = 10
        with multiprocessing.Manager() as manager:
            q1 = manager.Queue(maxsize = n * buffer_ratio)
            q2 = manager.Queue()
            o = manager.dict()
            read_process = multiprocessing.Process(target=Multi.mp_reader,
                                                   args=(ps_table.get_rows,interval_set,q1,n))
            read_process.start()
            pool = [multiprocessing.Process(target=Multi.mp_do_rows,args=(q1,self.row_fit_beta,group_indices,q2)) for n in range(n-2)] 
            for p in pool:
                p.start()
            done_count = 0
            while True:
                item = q2.get()
                if item == "DONE":
                    done_count += 1
                    if done_count == n-2:
                        break
                    continue
                beta_stats[item[0]] = item[1]
            read_process.join()
            for p in pool:
                p.join()
        return beta_stats
    

    def row_query_beta(self,row,beta_stats):
        interval,values = row
        probabilities = []
        for mab in beta_stats[interval]:
            if None in mab:
                probabilities.append([float('nan') for i in range(len(values))])
                continue
            m,a,b = mab
            sub_probs = []
            for x in values:
                sub_probs.append(self.beta.cdf(x,m,a,b))
            probabilities.append(sub_probs)
        return probabilities

    def query(self,ps_table,groups,beta_stats):
        import multiprocessing
        interval_set = set(beta_stats.keys())
        n = 12
        buffer_ratio = 10
        with multiprocessing.Manager() as manager:
            q1 = manager.Queue(maxsize = n * buffer_ratio)
            q2 = manager.Queue()
            o = manager.dict()
            samples = ps_table.get_samples()
            print("get samples",samples)
            probs_by_sample = [[[] for j in range(len(samples))] for i in range(len(groups))]
            read_process = multiprocessing.Process(target=Multi.mp_reader,args=(ps_table.get_rows,interval_set,q1,n))
            read_process.start()
            pool = [multiprocessing.Process(target=Multi.mp_do_rows,args=(q1,self.row_query_beta,beta_stats,q2)) for n in range(n-2)] 
            for p in pool:
                p.start()
                print("p.started")
            done_count = 0
            loop_count = 0
            while True:
                item = q2.get()
                if item == "DONE":
                    done_count += 1
                    if done_count == n-2:
                        break
                    continue
                for i,sub_probs in enumerate(item):
                    for j,prob in enumerate(sub_probs):
                        probs_by_sample[i][j].append(prob)
                loop_count += 1
            read_process.join()
            for p in pool:
                p.join()
        a = len(probs_by_sample)
        pvals = [[[1 for k in range(len(samples))] for j in range(len(groups))] for i in range(len(groups))]
        queries = [[f"{group_i}_over_{group_j}" for group_j in groups] for group_i in groups]

        for i,group_of_probs in enumerate(probs_by_sample):
            for j,comp_group_probs in enumerate(probs_by_sample):

                if i==j:
                    continue
                for k,pair in enumerate(zip(group_of_probs,comp_group_probs)):
                    first,second = pair
                    s,pval = ranksums(first,second,alternative="greater",nan_policy="omit")
                    pvals[i][j][k] = pval
        return samples,queries,pvals
    

#### Signature Class ####    
class Signature:
    def __init__(self,label=None,manifest=None,samples=[],control_group=None):
        
        # Saving or instantiating sample group information
        self.label = label
        self.manifest = manifest
        self.samples = samples
        self.control = control_group

    def add_sample(self,sample):
        self.samples.append(sample)
        
    def add_control(self,control_group):
        self.control = control_group
        


        
# Run main
if __name__ == "__main__":
    main()


