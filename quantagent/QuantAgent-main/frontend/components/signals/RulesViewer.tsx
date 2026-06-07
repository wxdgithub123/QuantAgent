"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FactorDictionary } from "./FactorDictionary";
import { StrategySystem } from "./StrategySystem";

export function RulesViewer() {
  return (
    <Card className="border-cyan-500/20">
      <CardHeader className="pb-3">
        <CardTitle className="text-base text-foreground flex items-center gap-2">
          📋 规则查看
        </CardTitle>
        <p className="text-xs text-muted-foreground">
          先理解因子和策略的定义，再看它们在具体交易对和时间点上的实际表现。
        </p>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="factors">
          <TabsList className="bg-secondary border border-border mb-4">
            <TabsTrigger value="factors" className="text-muted-foreground data-[state=active]:text-blue-400 text-xs">
              因子字典
            </TabsTrigger>
            <TabsTrigger value="strategies" className="text-muted-foreground data-[state=active]:text-orange-400 text-xs">
              策略体系
            </TabsTrigger>
          </TabsList>
          <TabsContent value="factors">
            <FactorDictionary />
          </TabsContent>
          <TabsContent value="strategies">
            <StrategySystem />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
